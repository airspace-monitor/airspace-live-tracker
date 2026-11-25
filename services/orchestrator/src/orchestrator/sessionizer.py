"""`flights_sessionizer` (docs/04-pipelines.md#flights_sessionizer): `core.flights` every 5 min.

Each run reads the window's points (`[window_start, window_end)`, the last 30 min) plus 20 min
before it as context, and feeds each aircraft's points after its latest stored flight's
`last_seen` to `flights.Sessionizer`. Points at or before that frontier were processed already
(or arrive too late and are left to `flights_rebuild`), so replaying a window changes nothing.

Then, against the watermark (min(now − 10 min, latest successful snapshot)): open flights whose
last point is more than 20 min before it close; closed flights whose `last_seen` is before it are
finalised and never touched again. Runs are serialised with an advisory lock.
"""

import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import astuple, fields
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
from dagster import (
    Config,
    DefaultScheduleStatus,
    OpExecutionContext,
    RunRequest,
    ScheduleEvaluationContext,
    job,
    op,
    schedule,
)

from airspace_common.settings import JobsSettings
from orchestrator.flights import MAX_GAP, Airport, Flight, Point, Sessionizer
from orchestrator.job_runs import recorded_run

WINDOW = timedelta(minutes=30)
STEP = timedelta(minutes=5)
WATERMARK_LAG = timedelta(minutes=10)
METAR_MAX_AGE = timedelta(minutes=90)
LOCK_KEY = 0x5E55_1011  # pg_advisory_xact_lock key for this job

POINT_COLS = (
    "snapshot_time, callsign, time_position, lat, lon, baro_altitude_m, geo_altitude_m, on_ground"
)
FLIGHT_COLS = tuple(f.name for f in fields(Flight) if f.name != "changed")


def _point(row: tuple[Any, ...]) -> Point:
    t, callsign, time_position, lat, lon, baro, geo, on_ground = row
    callsign = (callsign or "").strip() or None
    return Point(t, callsign, time_position, lat, lon, baro, geo, on_ground is True)


def _flight(row: tuple[Any, ...]) -> Flight:
    return Flight(**dict(zip(FLIGHT_COLS, row, strict=True)))


def watermark(conn: psycopg.Connection, now: datetime) -> datetime:
    row = conn.execute(
        "SELECT max(snapshot_time) FROM ops.ingest_batches"
        " WHERE query_kind = 'states_global' AND http_status = 200"
    ).fetchone()
    latest = row[0] if row else None
    lagged = now - WATERMARK_LAG
    return lagged if latest is None else min(lagged, latest)


def target_airports(conn: psycopg.Connection) -> list[Airport]:
    rows = conn.execute(
        "SELECT icao, lat, lon, elevation_m FROM ref.airports WHERE is_target ORDER BY icao"
    ).fetchall()
    return [Airport(*r) for r in rows]


class Qnh:
    """The QNH observed at a station within 90 min before a time (docs/04 height rule)."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn

    def __call__(self, station: str, at: datetime) -> float | None:
        row = self.conn.execute(
            "SELECT qnh_hpa FROM core.metar WHERE station = %s AND observed_at <= %s"
            " AND observed_at > %s AND qnh_hpa IS NOT NULL ORDER BY observed_at DESC LIMIT 1",
            (station, at, at - METAR_MAX_AGE),
        ).fetchone()
        return None if row is None else float(row[0])


def fetch_points(
    conn: psycopg.Connection, start: datetime, end: datetime
) -> dict[str, list[Point]]:
    by_aircraft: dict[str, list[Point]] = defaultdict(list)
    with conn.cursor(name="sessionizer_points") as cur:
        cur.itersize = 50_000
        cur.execute(
            f"SELECT icao24, {POINT_COLS} FROM raw.state_vectors"
            " WHERE snapshot_time >= %s AND snapshot_time < %s ORDER BY icao24, snapshot_time",
            (start - MAX_GAP, end),
        )
        for row in cur:
            by_aircraft[row[0]].append(_point(row[1:]))
    return by_aircraft


def latest_flights(conn: psycopg.Connection, icao24s: list[str]) -> dict[str, Flight]:
    rows = conn.execute(
        f"SELECT DISTINCT ON (icao24) {', '.join(FLIGHT_COLS)} FROM core.flights"
        " WHERE icao24 = ANY(%s) ORDER BY icao24, last_seen DESC",
        (icao24s,),
    ).fetchall()
    return {r[1]: _flight(r) for r in rows}


def stale_active(conn: psycopg.Connection, before: datetime) -> list[Flight]:
    rows = conn.execute(
        f"SELECT {', '.join(FLIGHT_COLS)} FROM core.flights"
        " WHERE status = 'active' AND last_seen < %s",
        (before,),
    ).fetchall()
    return [_flight(r) for r in rows]


def last_points(conn: psycopg.Connection, flights: list[Flight]) -> dict[uuid.UUID, Point]:
    if not flights:
        return {}
    rows = conn.execute(
        f"SELECT s.icao24, {', '.join('s.' + c.strip() for c in POINT_COLS.split(','))}"
        " FROM raw.state_vectors s"
        " JOIN unnest(%s::text[], %s::timestamptz[]) AS k(icao24, t)"
        " ON s.icao24 = k.icao24 AND s.snapshot_time = k.t",
        ([f.icao24 for f in flights], [f.last_seen for f in flights]),
    ).fetchall()
    found = {(r[0], r[1]): _point(r[1:]) for r in rows}
    return {
        f.flight_id: found[(f.icao24, f.last_seen)]
        for f in flights
        if (f.icao24, f.last_seen) in found
    }


def sessionize(
    conn: psycopg.Connection, start: datetime, end: datetime, now: datetime
) -> dict[str, int]:
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_KEY,))
    mark = watermark(conn, now)
    engine = Sessionizer(target_airports(conn), Qnh(conn))
    points = fetch_points(conn, start, end)
    latest = latest_flights(conn, list(points))

    changed: dict[uuid.UUID, Flight] = {}
    for icao24, pts in points.items():
        stored = latest.get(icao24)
        frontier = stored.last_seen if stored else None
        context = None
        new: list[Point] = []
        for p in pts:
            if (frontier is not None and p.t <= frontier) or p.t < start:
                context = p
            else:
                new.append(p)
        if stored is not None and stored.finalized:
            stored = None  # finalised flights are never extended
        for f in engine.feed(icao24, stored, context, new):
            changed[f.flight_id] = f

    # Open flights whose last point is more than 20 min before the watermark close.
    stale = [f for f in stale_active(conn, mark - MAX_GAP) if f.flight_id not in changed]
    stale += [f for f in changed.values() if f.status == "active" and f.last_seen < mark - MAX_GAP]
    lasts = last_points(conn, stale)
    for f in stale:
        engine.close(f, lasts.get(f.flight_id))
        changed[f.flight_id] = f

    written = write(conn, changed.values())
    cur = conn.execute(
        "UPDATE core.flights SET finalized = true, updated_at = now()"
        " WHERE status <> 'active' AND NOT finalized AND last_seen < %s",
        (mark,),
    )
    return {
        "aircraft": len(points),
        "written": written,
        "closed_stale": len(stale),
        "finalized": cur.rowcount,
    }


def write(conn: psycopg.Connection, flights: Iterable[Flight]) -> int:
    """Updates existing flights first (a flight closing frees its aircraft's one `active` slot),
    then inserts new ones."""
    rows = [astuple(f)[: len(FLIGHT_COLS)] for f in flights]
    if not rows:
        return 0
    cols = ", ".join(FLIGHT_COLS)
    with conn.cursor() as cur:
        cur.execute(
            f"CREATE TEMP TABLE stage_flights ON COMMIT DROP AS SELECT {cols}"
            " FROM core.flights WITH NO DATA"
        )
        with cur.copy(f"COPY stage_flights ({cols}) FROM STDIN") as copy:
            for row in rows:
                copy.write_row(row)
        sets = ", ".join(f"{c} = s.{c}" for c in FLIGHT_COLS if c != "flight_id")
        cur.execute(
            f"UPDATE core.flights f SET {sets}, updated_at = now() FROM stage_flights s"
            " WHERE f.flight_id = s.flight_id"
        )
        updated = cur.rowcount
        cur.execute(
            f"INSERT INTO core.flights ({cols}) SELECT {cols} FROM stage_flights s"
            " WHERE NOT EXISTS (SELECT 1 FROM core.flights f WHERE f.flight_id = s.flight_id)"
        )
        return updated + cur.rowcount


class FlightsWindow(Config):
    """The explicit `[window_start, window_end)` (ISO 8601 with a UTC offset)."""

    window_start: str
    window_end: str


@op
def flights_sessionizer_op(context: OpExecutionContext, config: FlightsWindow) -> None:
    start = datetime.fromisoformat(config.window_start)
    end = datetime.fromisoformat(config.window_end)
    settings = JobsSettings()
    with recorded_run(settings, "flights_sessionizer", start, end) as run:
        stats = sessionize(run.conn, start, end, datetime.now(UTC))
        run.rows_out = stats["written"]
    context.log.info(f"{stats}")


@job(description="Sessionize the last 30 min of state vectors into core.flights.")
def flights_sessionizer() -> None:
    flights_sessionizer_op()


def window_for_tick(tick: datetime) -> tuple[datetime, datetime]:
    return tick - WINDOW, tick


@schedule(
    job=flights_sessionizer,
    cron_schedule="*/5 * * * *",
    execution_timezone="UTC",
    default_status=DefaultScheduleStatus.RUNNING,
)
def flights_sessionizer_schedule(context: ScheduleEvaluationContext) -> RunRequest:
    tick = context.scheduled_execution_time or datetime.now(UTC)
    start, end = window_for_tick(tick.astimezone(UTC))
    window = {"window_start": start.isoformat(), "window_end": end.isoformat()}
    return RunRequest(
        run_key=window["window_end"],
        run_config={"ops": {"flights_sessionizer_op": {"config": window}}},
    )
