"""`flight_labels_merge` (docs/04-pipelines.md#flight_labels_merge): OpenSky route labels.

Daily at 08:00 for yesterday, two hours after the collector fetched yesterday's flight lists. Each
finalized `core.flights` row whose `first_seen` lies in the window is matched to the
`raw.opensky_flights` row of the same aircraft whose `first_seen` is closest to its own, at most
30 min away. That row's estimated airports become `dep_icao` / `arr_icao` with source `opensky`;
an `observed` value is never overwritten and a NULL estimate changes nothing. Re-running a window
writes the same values, so it updates nothing.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

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
from orchestrator.job_runs import recorded_run

MAX_OFFSET = timedelta(minutes=30)


@dataclass(frozen=True)
class Label:
    first_seen: datetime
    est_dep_icao: str | None
    est_arr_icao: str | None


@dataclass(frozen=True)
class Labels:
    """A flight's departure and arrival with their sources."""

    dep_icao: str | None
    dep_source: str | None
    arr_icao: str | None
    arr_source: str | None


def nearest(first_seen: datetime, candidates: list[Label]) -> Label | None:
    """The candidate whose `first_seen` is closest, at most 30 min away (the earlier on a tie)."""
    close = [c for c in candidates if abs(c.first_seen - first_seen) <= MAX_OFFSET]
    return min(close, key=lambda c: (abs(c.first_seen - first_seen), c.first_seen), default=None)


def merge(current: Labels, label: Label) -> Labels:
    """`current` with the label's estimates filled in where they are not `observed`."""
    dep, dep_source = current.dep_icao, current.dep_source
    if label.est_dep_icao is not None and dep_source != "observed":
        dep, dep_source = label.est_dep_icao, "opensky"
    arr, arr_source = current.arr_icao, current.arr_source
    if label.est_arr_icao is not None and arr_source != "observed":
        arr, arr_source = label.est_arr_icao, "opensky"
    return Labels(dep, dep_source, arr, arr_source)


def merge_window(conn: psycopg.Connection, start: datetime, end: datetime) -> int:
    """Labels the window's finalized flights and returns how many rows changed."""
    flights = conn.execute(
        "SELECT flight_id, icao24, first_seen, dep_icao, dep_source, arr_icao, arr_source"
        " FROM core.flights WHERE finalized AND first_seen >= %s AND first_seen < %s",
        (start, end),
    ).fetchall()
    if not flights:
        return 0
    rows = conn.execute(
        "SELECT icao24, first_seen, est_dep_icao, est_arr_icao FROM raw.opensky_flights"
        " WHERE first_seen >= %s AND first_seen <= %s AND icao24 = ANY(%s)",
        (start - MAX_OFFSET, end + MAX_OFFSET, list({f[1] for f in flights})),
    ).fetchall()
    by_aircraft: dict[str, list[Label]] = defaultdict(list)
    for icao24, first_seen, dep, arr in rows:
        by_aircraft[icao24].append(Label(first_seen, dep, arr))

    updates: list[tuple[uuid.UUID, Labels]] = []
    for flight_id, icao24, first_seen, *labels in flights:
        label = nearest(first_seen, by_aircraft.get(icao24, []))
        if label is None:
            continue
        current = Labels(*labels)
        merged = merge(current, label)
        if merged != current:
            updates.append((flight_id, merged))
    if not updates:
        return 0
    cur = conn.execute(
        "UPDATE core.flights f SET dep_icao = u.dep_icao, dep_source = u.dep_source,"
        " arr_icao = u.arr_icao, arr_source = u.arr_source, updated_at = now()"
        " FROM unnest(%s::uuid[], %s::text[], %s::text[], %s::text[], %s::text[])"
        " AS u(flight_id, dep_icao, dep_source, arr_icao, arr_source)"
        " WHERE f.flight_id = u.flight_id",
        (
            [i for i, _ in updates],
            [m.dep_icao for _, m in updates],
            [m.dep_source for _, m in updates],
            [m.arr_icao for _, m in updates],
            [m.arr_source for _, m in updates],
        ),
    )
    return cur.rowcount


class LabelsWindow(Config):
    """The explicit `[window_start, window_end)` of flights' `first_seen` (ISO 8601 with offset)."""

    window_start: str
    window_end: str


@op
def flight_labels_merge_op(context: OpExecutionContext, config: LabelsWindow) -> None:
    start = datetime.fromisoformat(config.window_start)
    end = datetime.fromisoformat(config.window_end)
    settings = JobsSettings()
    with recorded_run(settings, "flight_labels_merge", start, end) as run:
        run.rows_out = merge_window(run.conn, start, end)
    context.log.info(f"labelled {run.rows_out} flights")


@job(description="Copy OpenSky's estimated airports onto yesterday's finalized flights.")
def flight_labels_merge() -> None:
    flight_labels_merge_op()


def window_for_tick(tick: datetime) -> tuple[datetime, datetime]:
    """Yesterday: the UTC day before the tick's."""
    end = datetime.combine(tick.astimezone(UTC).date(), time(), UTC)
    return end - timedelta(days=1), end


@schedule(
    job=flight_labels_merge,
    cron_schedule="0 8 * * *",
    execution_timezone="UTC",
    default_status=DefaultScheduleStatus.RUNNING,
)
def flight_labels_merge_schedule(context: ScheduleEvaluationContext) -> RunRequest:
    tick = context.scheduled_execution_time or datetime.now(UTC)
    start, end = window_for_tick(tick)
    window = {"window_start": start.isoformat(), "window_end": end.isoformat()}
    return RunRequest(
        run_key=window["window_end"],
        run_config={"ops": {"flight_labels_merge_op": {"config": window}}},
    )
