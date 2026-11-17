"""Daily spool compaction to Parquet (docs/04-pipelines.md#p1--collector, "Archive").

At 00:30 UTC every finished day whose files have all been uploaded (`sent/`, none left in
`pending/`) is written to `archive/states/YYYY-MM-DD.parquet` and
`archive/flights/YYYY-MM-DD.parquet`, then that day's JSON files are deleted. A file's day is
the time in its UUIDv7 batch id (written seconds after the request), so days are found from file
names without opening them.

Rows keep OpenSky's original fields plus each batch's envelope, so `collector.replay` can rebuild
the exact batches. Failed requests carry no rows; they stay explained by `ops.ingest_batches`.
States are written hour by hour, sorted by `icao24` then `snapshot_time` within each hour: a
whole-day sort needs ~3.5 GB, more than the Pi has.

Safety: an archive is written to a temporary file, fsynced, renamed, and its row count checked
before any JSON is deleted. An existing archive is never overwritten.
"""

import asyncio
import gzip
import json
import os
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import structlog

from collector.archive_upload import ArchiveUploader
from collector.spool import Spool

log = structlog.get_logger()

RUN_AT = time(0, 30)

STATE_FIELDS: list[tuple[str, pa.DataType]] = [
    ("icao24", pa.string()), ("callsign", pa.string()), ("origin_country", pa.string()),
    ("time_position", pa.int64()), ("last_contact", pa.int64()), ("longitude", pa.float64()),
    ("latitude", pa.float64()), ("baro_altitude", pa.float64()), ("on_ground", pa.bool_()),
    ("velocity", pa.float64()), ("true_track", pa.float64()), ("vertical_rate", pa.float64()),
    ("sensors", pa.list_(pa.int64())), ("geo_altitude", pa.float64()), ("squawk", pa.string()),
    ("spi", pa.bool_()), ("position_source", pa.int8()), ("category", pa.int8()),
]  # fmt: skip
FLIGHT_FIELDS: list[tuple[str, pa.DataType]] = [
    ("icao24", pa.string()), ("firstSeen", pa.int64()), ("estDepartureAirport", pa.string()),
    ("lastSeen", pa.int64()), ("estArrivalAirport", pa.string()), ("callsign", pa.string()),
    ("estDepartureAirportHorizDistance", pa.int64()),
    ("estDepartureAirportVertDistance", pa.int64()),
    ("estArrivalAirportHorizDistance", pa.int64()),
    ("estArrivalAirportVertDistance", pa.int64()),
    ("departureAirportCandidatesCount", pa.int64()), ("arrivalAirportCandidatesCount", pa.int64()),
]  # fmt: skip
TS = pa.timestamp("us", tz="UTC")
BATCH_FIELDS: list[tuple[str, pa.DataType]] = [
    ("batch_id", pa.string()), ("collector_id", pa.string()), ("requested_at", TS),
    ("credits_remaining", pa.int32()),
]  # fmt: skip
STATES_SCHEMA = pa.schema([*BATCH_FIELDS, ("snapshot_time", TS), *STATE_FIELDS])
FLIGHTS_SCHEMA = pa.schema(
    [*BATCH_FIELDS, ("window_begin", TS), ("window_end", TS), *FLIGHT_FIELDS]
)


def batch_time(batch_id: str) -> datetime:
    """The UUIDv7 timestamp of a batch id."""
    return datetime.fromtimestamp((UUID(batch_id).int >> 80) / 1000, UTC)


def _batch_id(path: Path) -> str:
    return path.name.split(".", 1)[0]


def _day(path: Path) -> date:
    return batch_time(_batch_id(path)).date()


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _read(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        envelope: dict[str, Any] = json.load(f)
    return envelope


def _batch_columns(env: dict[str, Any]) -> dict[str, Any]:
    return {
        "batch_id": env["batch_id"],
        "collector_id": env["collector_id"],
        "requested_at": _parse_ts(env["requested_at"]),
        "credits_remaining": env.get("credits_remaining"),
    }


def _state_rows(env: dict[str, Any]) -> list[dict[str, Any]]:
    body = env.get("response")
    if env.get("http_status") != 200 or not isinstance(body, dict):
        return []
    batch = _batch_columns(env) | {"snapshot_time": datetime.fromtimestamp(body["time"], UTC)}
    rows = []
    for vector in body.get("states") or []:
        padded = list(vector) + [None] * (len(STATE_FIELDS) - len(vector))
        rows.append(batch | dict(zip((n for n, _ in STATE_FIELDS), padded, strict=False)))
    return rows


def _flight_rows(env: dict[str, Any]) -> list[dict[str, Any]]:
    body = env.get("response")
    if env.get("http_status") != 200 or not isinstance(body, list):
        return []
    batch = _batch_columns(env) | {
        "window_begin": _parse_ts(env["query"]["begin"]),
        "window_end": _parse_ts(env["query"]["end"]),
    }
    return [batch | {n: f.get(n) for n, _ in FLIGHT_FIELDS} for f in body]


class _DayWriter:
    """One day's archive of one kind, written hour by hour to a temporary file. An archive that
    already exists is left untouched; its batch ids are read back for the clean-up check."""

    def __init__(self, path: Path, schema: pa.Schema, sort_keys: list[tuple[str, str]]) -> None:
        self.path, self.schema, self.sort_keys = path, schema, sort_keys
        self.tmp = path.with_name(path.name + ".tmp")
        self.existing = path.exists()
        self.writer: pq.ParquetWriter | None = None
        self.hour: list[pa.Table] = []
        self.batch_ids: set[str] = set()
        self.rows = 0

    def add(self, batch_id: str, rows: list[dict[str, Any]]) -> None:
        if rows and not self.existing:
            self.hour.append(pa.Table.from_pylist(rows, schema=self.schema))
            self.batch_ids.add(batch_id)

    def end_hour(self) -> None:
        if not self.hour:
            return
        table = pa.concat_tables(self.hour)
        self.hour = []
        if self.sort_keys:
            table = table.sort_by(self.sort_keys)
        if self.writer is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.writer = pq.ParquetWriter(self.tmp, self.schema, compression="zstd")
        self.writer.write_table(table)
        self.rows += len(table)

    def finish(self) -> int | None:
        """Renames the archive into place after checking its row count; None if nothing new."""
        if self.writer is None:
            return None
        self.writer.close()
        with open(self.tmp, "r+b") as f:  # writable, so fsync also works on Windows
            os.fsync(f.fileno())
        if pq.read_metadata(self.tmp).num_rows != self.rows:
            raise RuntimeError(f"{self.tmp}: row count differs from the {self.rows} written")
        os.replace(self.tmp, self.path)
        return self.rows

    def archived_ids(self) -> set[str]:
        if not self.existing:
            return self.batch_ids
        ids = pc.unique(pq.read_table(self.path, columns=["batch_id"]).column("batch_id"))
        return set(ids.to_pylist())


def compact_day(spool: Spool, day: date, files: list[Path]) -> None:
    """Reads each file once, writes both archives, then deletes the JSON they cover."""
    archive = spool.root / "archive"
    states = _DayWriter(
        archive / "states" / f"{day.isoformat()}.parquet",
        STATES_SCHEMA,
        [("icao24", "ascending"), ("snapshot_time", "ascending")],
    )
    flights = _DayWriter(archive / "flights" / f"{day.isoformat()}.parquet", FLIGHTS_SCHEMA, [])
    by_hour: dict[int, list[Path]] = defaultdict(list)
    for path in files:
        by_hour[batch_time(_batch_id(path)).hour].append(path)

    seen: list[tuple[Path, str, bool]] = []  # path, batch id, has rows
    for hour in sorted(by_hour):
        for path in by_hour[hour]:
            env = _read(path)
            state_rows, flight_rows = _state_rows(env), _flight_rows(env)
            states.add(env["batch_id"], state_rows)
            flights.add(env["batch_id"], flight_rows)
            seen.append((path, env["batch_id"], bool(state_rows or flight_rows)))
        states.end_hour()
        flights.end_hour()
    written = {"states": states.finish(), "flights": flights.finish()}

    # Delete only JSON whose rows are in an archive (files without rows can always go).
    archived = states.archived_ids() | flights.archived_ids()
    deleted = kept = 0
    for path, batch_id, has_rows in seen:
        if not has_rows or batch_id in archived:
            path.unlink()
            deleted += 1
        else:
            kept += 1
    log.info("archive_day", day=day.isoformat(), rows=written, deleted=deleted, kept=kept)
    if kept:
        log.warning("archive_day_unarchived_files", day=day.isoformat(), files=kept)


def compact_ready_days(spool: Spool, now: datetime) -> list[date]:
    """Compacts every day before `now`'s UTC day whose files are all in `sent/`."""
    today = now.astimezone(UTC).date()
    sent: dict[date, list[Path]] = defaultdict(list)
    for path in (spool.root / "sent").glob("*.json.gz"):
        sent[_day(path)].append(path)
    pending_days = {_day(p) for p in (spool.root / "pending").glob("*.json.gz")}
    done = []
    for day in sorted(sent):
        if day >= today or day in pending_days:
            continue
        before = {p.name for p in (spool.root / "archive").rglob("*.parquet")}
        compact_day(spool, day, sorted(sent[day]))
        after = {p.name for p in (spool.root / "archive").rglob("*.parquet")}
        if after - before:
            done.append(day)
    return done


def next_run(now: datetime) -> datetime:
    run = datetime.combine(now.astimezone(UTC).date(), RUN_AT, UTC)
    return run if run > now else run + timedelta(days=1)


async def run_archive(spool: Spool, uploader: "ArchiveUploader | None" = None) -> None:
    """Daily at 00:30 UTC: compact, then (with R2 configured) upload and apply retention."""
    if uploader is None:
        log.warning("archive_upload_not_configured", detail="set R2_ACCOUNT_ID and R2 keys")
    while True:
        now = datetime.now(UTC)
        await asyncio.sleep((next_run(now) - now).total_seconds())
        try:
            days = await asyncio.to_thread(compact_ready_days, spool, datetime.now(UTC))
            log.info("archive_run", days=[d.isoformat() for d in days])
        except Exception:
            log.exception("archive_run_crashed")
        if uploader is not None:
            try:
                await asyncio.to_thread(uploader.run, datetime.now(UTC).date())
            except Exception:
                log.exception("archive_upload_failed")
