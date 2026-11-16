"""`collector_gap_check` (docs/04-pipelines.md#collector_gap_check).

A gap is a run of at least 4 consecutive slots on a collector's 90 s grid without a successful
`states_global` batch. Each gap becomes one `collector_gap` event, keyed by its first missed slot,
so re-running a window (or overlapping windows) never duplicates an event. A gap that began
before the window keeps its real start: the last success before the window is looked up.
A collector with no success yet (never started) has no gap.
"""

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

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

CADENCE_S = 90
MIN_MISSED_SLOTS = 4
WINDOW = timedelta(hours=2)
# Slots this close to the tick are not judged yet: a response can take ~45 s and the upload
# follows it.
UPLOAD_GRACE = timedelta(minutes=5)


def slot_of(ts: datetime, offset_s: int, cadence_s: int = CADENCE_S) -> datetime:
    """The start of the grid slot a request made at `ts` belongs to."""
    epoch = ts.timestamp() - offset_s
    return datetime.fromtimestamp(epoch - epoch % cadence_s + offset_s, UTC)


def find_gaps(
    ok_slots: Iterable[datetime],
    last_ok_before: datetime | None,
    start: datetime,
    end: datetime,
    cadence_s: int = CADENCE_S,
    min_missed: int = MIN_MISSED_SLOTS,
    offset_s: int = 0,
) -> list[datetime]:
    """First missed slot of every gap among the slots in `[start, end)`."""
    step = timedelta(seconds=cadence_s)
    ok = set(ok_slots)
    first = slot_of(start, offset_s, cadence_s)
    if first < start:
        first += step
    gaps: list[datetime] = []
    # A run of misses may already be going on when the window opens.
    run_start: datetime | None = (last_ok_before + step) if last_ok_before else None
    if run_start is not None and run_start >= first:
        run_start = None

    def close(run_end: datetime) -> None:
        if run_start is not None and (run_end - run_start) // step >= min_missed:
            gaps.append(run_start)

    # Misses before a collector's first ever success are not a gap: it had not started yet.
    started = last_ok_before is not None
    slot = first
    while slot < end:
        if slot in ok:
            close(slot)
            run_start = None
            started = True
        elif started and run_start is None:
            run_start = slot
        slot += step
    close(slot)
    return gaps


COLLECTORS_SQL = "SELECT collector_id, offset_seconds FROM ops.collectors WHERE disabled_at IS NULL"
OK_REQUESTS_SQL = """
SELECT requested_at FROM ops.ingest_batches
WHERE collector_id = %s AND query_kind = 'states_global' AND http_status = 200
  AND requested_at >= %s AND requested_at < %s
"""
LAST_OK_SQL = """
SELECT max(requested_at) FROM ops.ingest_batches
WHERE collector_id = %s AND query_kind = 'states_global' AND http_status = 200 AND requested_at < %s
"""
INSERT_EVENT_SQL = """
INSERT INTO core.events (dedupe_key, ts, kind, severity, title, payload)
VALUES (%s, %s, 'collector_gap', 'warn', %s, %s)
ON CONFLICT (dedupe_key) DO NOTHING
"""


def check_window(conn: psycopg.Connection, start: datetime, end: datetime) -> int:
    """Inserts the window's `collector_gap` events and returns how many were new."""
    new = 0
    for collector_id, offset_s in conn.execute(COLLECTORS_SQL).fetchall():
        rows = conn.execute(OK_REQUESTS_SQL, (collector_id, start, end)).fetchall()
        ok = {slot_of(r[0], offset_s) for r in rows}
        last_ok = conn.execute(LAST_OK_SQL, (collector_id, start)).fetchone()
        last_ok_slot = slot_of(last_ok[0], offset_s) if last_ok and last_ok[0] else None
        for gap_start in find_gaps(ok, last_ok_slot, start, end, offset_s=offset_s):
            key = f"collector_gap:{collector_id}:{gap_start.strftime('%Y-%m-%dT%H:%M:%SZ')}"
            title = f"No data from {collector_id} since {gap_start:%Y-%m-%d %H:%M} UTC"
            payload = psycopg.types.json.Jsonb(
                {"collector_id": collector_id, "gap_start": gap_start.isoformat()}
            )
            cur = conn.execute(INSERT_EVENT_SQL, (key, gap_start, title, payload))
            new += cur.rowcount
    return new


class GapWindow(Config):
    """The explicit `[window_start, window_end)` (ISO 8601 with a UTC offset)."""

    window_start: str
    window_end: str


@op
def collector_gap_check_op(context: OpExecutionContext, config: GapWindow) -> None:
    start = datetime.fromisoformat(config.window_start)
    end = datetime.fromisoformat(config.window_end)
    settings = JobsSettings()
    with recorded_run(settings, "collector_gap_check", start, end) as run:
        run.rows_out = check_window(run.conn, start, end)
    context.log.info(f"{run.rows_out} new collector_gap events for [{start}, {end})")


@job(description="collector_gap events for runs of >= 4 slots without a successful snapshot.")
def collector_gap_check() -> None:
    collector_gap_check_op()


def window_for_tick(tick: datetime) -> tuple[datetime, datetime]:
    end = tick - UPLOAD_GRACE
    return end - WINDOW, end


@schedule(
    job=collector_gap_check,
    cron_schedule="*/5 * * * *",
    execution_timezone="UTC",
    default_status=DefaultScheduleStatus.RUNNING,
)
def collector_gap_check_schedule(context: ScheduleEvaluationContext) -> RunRequest:
    tick = context.scheduled_execution_time or datetime.now(UTC)
    start, end = window_for_tick(tick.astimezone(UTC))
    window = {"window_start": start.isoformat(), "window_end": end.isoformat()}
    return RunRequest(
        run_key=window["window_end"],
        run_config={"ops": {"collector_gap_check_op": {"config": window}}},
    )
