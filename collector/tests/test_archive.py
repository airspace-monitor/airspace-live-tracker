import gzip
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pyarrow.parquet as pq

from collector.archive import batch_time, compact_ready_days
from collector.spool import Spool

DAY1 = datetime(2026, 11, 15, tzinfo=UTC)
DAY2 = datetime(2026, 11, 16, tzinfo=UTC)


def uuid7_at(ts: datetime, n: int) -> str:
    """A UUIDv7 whose timestamp is `ts` (the spool names files by batch id)."""
    ms = int(ts.timestamp() * 1000)
    value = (ms << 80) | (0x7 << 76) | (n & 0xFFF) << 64 | (0b10 << 62) | n
    return str(UUID(int=value))


def state(icao24: str, lon: float = 16.5) -> list:
    # The 18 positional fields of an extended OpenSky state vector.
    return [
        icao24,
        "SWR283  ",
        "Switzerland",
        1,
        2,
        lon,
        48.1,
        10000.0,
        False,
        230.0,
        90.0,
        -1.0,
        None,
        10100.0,
        "2331",
        False,
        0,
        4,
    ]


def write_batch(
    dir_: Path,
    ts: datetime,
    n: int,
    states: list | None,
    kind: str = "states_global",
    http_status: int = 200,
) -> str:
    batch_id = uuid7_at(ts, n)
    if kind == "states_global":
        query = {"kind": kind, "extended": True}
        response = {"time": int(ts.timestamp()), "states": states} if http_status == 200 else None
    else:
        query = {"kind": kind, "begin": "2026-11-14T00:00:00Z", "end": "2026-11-14T02:00:00Z"}
        response = states
    envelope = {
        "batch_id": batch_id,
        "collector_id": "pi-daniel",
        "query": query,
        "requested_at": ts.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "http_status": http_status,
        "retry_after_s": None,
        "credits_remaining": 3000,
        "response": response,
    }
    (dir_ / f"{batch_id}.json.gz").write_bytes(gzip.compress(json.dumps(envelope).encode()))
    return batch_id


def setup(tmp_path: Path) -> Spool:
    spool = Spool(tmp_path)
    sent = tmp_path / "sent"
    # Day 1: two hours, written newest hour first, aircraft out of order.
    write_batch(sent, DAY1 + timedelta(hours=1), 1, [state("bbbbbb"), state("aaaaaa")])
    write_batch(sent, DAY1 + timedelta(minutes=1), 2, [state("cccccc")])
    write_batch(sent, DAY1 + timedelta(minutes=3), 3, None, http_status=0)  # failed slot
    flight = {
        "icao24": "4b1805",
        "firstSeen": 1,
        "lastSeen": 2,
        "callsign": "SWR283  ",
        "estDepartureAirport": "LSZH",
        "estArrivalAirport": "LOWW",
    }
    write_batch(sent, DAY1 + timedelta(hours=6), 4, [flight], kind="flights_all")
    # Day 2: one uploaded file and one still waiting in pending/.
    write_batch(sent, DAY2 + timedelta(hours=2), 5, [state("dddddd")])
    write_batch(tmp_path / "pending", DAY2 + timedelta(hours=3), 6, [state("eeeeee")])
    return spool


NOW = datetime(2026, 11, 17, 0, 30, tzinfo=UTC)


def test_batch_time_reads_the_uuid7_timestamp() -> None:
    assert batch_time(uuid7_at(DAY1 + timedelta(seconds=90), 1)) == DAY1 + timedelta(seconds=90)


def test_a_finished_uploaded_day_becomes_parquet_and_its_json_is_deleted(tmp_path: Path) -> None:
    spool = setup(tmp_path)
    assert compact_ready_days(spool, NOW) == [date(2026, 11, 15)]
    states = pq.read_table(tmp_path / "archive/states/2026-11-15.parquet").to_pylist()
    assert [r["icao24"] for r in states] == ["cccccc", "aaaaaa", "bbbbbb"]  # by hour, then icao24
    assert states[0]["snapshot_time"] == DAY1 + timedelta(minutes=1)
    assert states[0]["collector_id"] == "pi-daniel"
    assert states[0]["category"] == 4 and states[0]["longitude"] == 16.5
    flights = pq.read_table(tmp_path / "archive/flights/2026-11-15.parquet").to_pylist()
    assert [(f["icao24"], f["estArrivalAirport"], f["window_begin"]) for f in flights] == [
        ("4b1805", "LOWW", datetime(2026, 11, 14, tzinfo=UTC))
    ]
    remaining = sorted(
        batch_time(p.name.split(".")[0]).date() for p in (tmp_path / "sent").iterdir()
    )
    assert remaining == [date(2026, 11, 16)]  # day 1's files, the failed slot included, are gone


def test_a_day_with_files_still_pending_is_left_alone(tmp_path: Path) -> None:
    setup(tmp_path)
    compact_ready_days(Spool(tmp_path), NOW)
    assert not (tmp_path / "archive/states/2026-11-16.parquet").exists()


def test_today_is_never_compacted(tmp_path: Path) -> None:
    setup(tmp_path)
    assert compact_ready_days(Spool(tmp_path), DAY1 + timedelta(hours=23)) == []


def test_a_second_run_changes_nothing(tmp_path: Path) -> None:
    spool = setup(tmp_path)
    compact_ready_days(spool, NOW)
    before = (tmp_path / "archive/states/2026-11-15.parquet").read_bytes()
    assert compact_ready_days(spool, NOW) == []
    assert (tmp_path / "archive/states/2026-11-15.parquet").read_bytes() == before


def test_an_existing_archive_is_never_overwritten(tmp_path: Path) -> None:
    # A crash after writing the archive but before deleting the JSON leaves both; the next run
    # must keep the archive and only finish the clean-up once the row counts match.
    spool = setup(tmp_path)
    compact_ready_days(spool, NOW)
    write_batch(tmp_path / "sent", DAY1 + timedelta(hours=1), 1, [state("bbbbbb"), state("aaaaaa")])
    compact_ready_days(spool, NOW)
    assert len(pq.read_table(tmp_path / "archive/states/2026-11-15.parquet")) == 3
