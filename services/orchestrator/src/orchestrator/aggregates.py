"""`agg_backfill_refresh` (docs/04-pipelines.md#agg_backfill_refresh).

The continuous aggregate's policy only refreshes the last 2 h. Batches that arrive later (a
drained backlog after an outage) are materialised here: successful `states_global` batches
received in the window whose `snapshot_time` is more than 2 h before `received_at` mark whole
UTC days to refresh.

Window (D11, resolves Q7): a scheduled run starts where the last successful run ended, so a
failed run never leaves late data unmaterialised; the first run looks back 65 min, and the
look-back is capped at 7 days.
"""

from collections.abc import Iterable
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

JOB = "agg_backfill_refresh"
LATE_AFTER = timedelta(hours=2)
FIRST_LOOKBACK = timedelta(minutes=65)
MAX_LOOKBACK = timedelta(days=7)


def days_to_refresh(late_snapshots: Iterable[datetime]) -> tuple[datetime, datetime] | None:
    """`[first day 00:00, day after the last day 00:00)` covering every late snapshot, in UTC."""
    times = [t.astimezone(UTC) for t in late_snapshots]
    if not times:
        return None
    first = datetime.combine(min(times).date(), time(), UTC)
    last = datetime.combine(max(times).date(), time(), UTC) + timedelta(days=1)
    return first, last


def scheduled_window(tick: datetime, last_ok_end: datetime | None) -> tuple[datetime, datetime]:
    start = last_ok_end if last_ok_end is not None else tick - FIRST_LOOKBACK
    return max(start, tick - MAX_LOOKBACK), tick


LAST_OK_END_SQL = "SELECT max(window_end) FROM ops.job_runs WHERE job = %s AND status = 'ok'"
LATE_SNAPSHOTS_SQL = """
SELECT DISTINCT snapshot_time FROM ops.ingest_batches
WHERE query_kind = 'states_global' AND http_status = 200
  AND received_at >= %s AND received_at < %s
  AND snapshot_time < received_at - %s
"""


class BackfillWindow(Config):
    """`window_end` is required (ISO 8601 with a UTC offset). Without `window_start` the run
    continues from the last successful run (see the module docstring)."""

    window_end: str
    window_start: str | None = None


def _last_ok_end(settings: JobsSettings) -> datetime | None:
    with psycopg.connect(
        host=settings.jobs_db_host,
        user="jobs",
        dbname="airspace",
        password=settings.jobs_password.get_secret_value(),
    ) as conn:
        row = conn.execute(LAST_OK_END_SQL, (JOB,)).fetchone()
    return row[0] if row else None


@op
def agg_backfill_refresh_op(context: OpExecutionContext, config: BackfillWindow) -> None:
    settings = JobsSettings()
    end = datetime.fromisoformat(config.window_end)
    if config.window_start:
        start = datetime.fromisoformat(config.window_start)
    else:
        start, end = scheduled_window(end, _last_ok_end(settings))
    # refresh_continuous_aggregate cannot run inside a transaction.
    with recorded_run(settings, JOB, start, end, autocommit=True) as run:
        late = [r[0] for r in run.conn.execute(LATE_SNAPSHOTS_SQL, (start, end, LATE_AFTER))]
        days = days_to_refresh(late)
        if days is None:
            run.rows_out = 0
            context.log.info(f"no late batches received in [{start}, {end})")
            return
        refresh_start, refresh_end = days[0], min(days[1], end)
        run.conn.execute(
            "CALL refresh_continuous_aggregate('agg.traffic_h3_15m', %s, %s)",
            (refresh_start, refresh_end),
        )
        run.rows_out = len(late)
    context.log.info(
        f"{len(late)} late snapshots received in [{start}, {end}); "
        f"refreshed agg.traffic_h3_15m for [{refresh_start}, {refresh_end})"
    )


@job(description="Materialise agg.traffic_h3_15m for days touched by late batches.")
def agg_backfill_refresh() -> None:
    agg_backfill_refresh_op()


@schedule(
    job=agg_backfill_refresh,
    cron_schedule="10 * * * *",
    execution_timezone="UTC",
    default_status=DefaultScheduleStatus.RUNNING,
)
def agg_backfill_refresh_schedule(context: ScheduleEvaluationContext) -> RunRequest:
    tick = (context.scheduled_execution_time or datetime.now(UTC)).astimezone(UTC)
    return RunRequest(
        run_key=tick.isoformat(),
        run_config={
            "ops": {"agg_backfill_refresh_op": {"config": {"window_end": tick.isoformat()}}}
        },
    )
