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
from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pyarrow as pa
import pyarrow.parquet as pq
import structlog

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


def _write_atomic(path: Path, schema: pa.Schema, row_groups: Iterable[list[dict[str, Any]]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    n = 0
    with pq.ParquetWriter(tmp, schema, compression="zstd") as writer:
        for rows in row_groups:
            if rows:
                writer.write_table(pa.Table.from_pylist(rows, schema=schema))
                n += len(rows)
    with open(tmp, "r+b") as f:  # writable, so fsync also works on Windows
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return n


def _archived_batch_ids(path: Path) -> set[str]:
    return set(pq.read_table(path, columns=["batch_id"]).column("batch_id").to_pylist())


def _hourly_rows(
    files: list[Path], to_rows: Callable[[dict[str, Any]], list[dict[str, Any]]], sort: bool
) -> Iterator[list[dict[str, Any]]]:
    """One row group per hour of batch time, optionally sorted by aircraft then snapshot."""
    by_hour: dict[int, list[Path]] = defaultdict(list)
    for path in files:
        by_hour[batch_time(_batch_id(path)).hour].append(path)
    for hour in sorted(by_hour):
        rows = [r for p in by_hour[hour] for r in to_rows(_read(p))]
        if sort:
            rows.sort(key=lambda r: (r["icao24"] or "", r["snapshot_time"]))
        yield rows


def compact_day(spool: Spool, day: date, files: list[Path]) -> None:
    states_path = spool.root / "archive" / "states" / f"{day.isoformat()}.parquet"
    flights_path = spool.root / "archive" / "flights" / f"{day.isoformat()}.parquet"
    by_kind: dict[str, list[Path]] = defaultdict(list)
    for path in files:
        by_kind[_read(path)["query"]["kind"]].append(path)

    written = {}
    for path_out, kind, schema, to_rows in (
        (states_path, "states_global", STATES_SCHEMA, _state_rows),
        (flights_path, "flights_all", FLIGHTS_SCHEMA, _flight_rows),
    ):
        kind_files = by_kind.get(kind, [])
        if path_out.exists() or not kind_files:
            continue
        sort = kind == "states_global"
        n = _write_atomic(path_out, schema, _hourly_rows(kind_files, to_rows, sort))
        if pq.read_metadata(path_out).num_rows != n:
            raise RuntimeError(f"{path_out}: wrote {n} rows but the file holds a different count")
        written[path_out.name] = n

    # Delete only JSON whose rows are in an archive (files without rows can always go).
    archived: set[str] = set()
    for path_out in (states_path, flights_path):
        if path_out.exists():
            archived |= _archived_batch_ids(path_out)
    deleted = kept = 0
    for path in files:
        env = _read(path)
        has_rows = bool(_state_rows(env) or _flight_rows(env))
        if not has_rows or env["batch_id"] in archived:
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


async def run_archive(spool: Spool) -> None:
    while True:
        now = datetime.now(UTC)
        await asyncio.sleep((next_run(now) - now).total_seconds())
        try:
            days = await asyncio.to_thread(compact_ready_days, spool, datetime.now(UTC))
            log.info("archive_run", days=[d.isoformat() for d in days])
        except Exception:
            log.exception("archive_run_crashed")
