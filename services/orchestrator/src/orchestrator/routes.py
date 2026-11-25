"""`routes_refresh` (docs/04-pipelines.md#routes_refresh): the route lookup `ref.callsign_routes`.

Daily at 08:30, after the collector's 06:00 flight-list fetch. Rebuilds the whole table from the
OpenSky flight lists (`raw.opensky_flights`) whose `first_seen` is in the 28 days before today:
for each callsign, every estimated arrival airport with its number of flights and its share of
the callsign's flights that have an arrival. The table is replaced in one transaction, and a
rebuild with under half the stored rows is refused (a collector outage, not a schedule change).
"""

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
from orchestrator.ref_refresh import check_shrink

LOOKBACK = timedelta(days=28)

ROUTES_SQL = """
CREATE TEMP TABLE stage_routes ON COMMIT DROP AS
SELECT callsign, destination, n_flights,
       (n_flights::double precision / sum(n_flights) OVER (PARTITION BY callsign))::real AS share,
       last_seen, 'opensky'::text AS source
FROM (
  SELECT callsign, est_arr_icao AS destination, count(*)::integer AS n_flights,
         max(first_seen AT TIME ZONE 'UTC')::date AS last_seen
  FROM raw.opensky_flights
  WHERE first_seen >= %s AND first_seen < %s
    AND callsign IS NOT NULL AND est_arr_icao IS NOT NULL
  GROUP BY callsign, est_arr_icao
) r
"""


def rebuild(conn: psycopg.Connection, start: datetime, end: datetime) -> int:
    """Replaces `ref.callsign_routes` with the window's routes; returns the number of rows."""
    conn.execute(ROUTES_SQL, (start, end))
    staged = conn.execute("SELECT count(*) FROM stage_routes").fetchone()[0]  # type: ignore[index]
    current = conn.execute("SELECT count(*) FROM ref.callsign_routes").fetchone()[0]  # type: ignore[index]
    check_shrink("ref.callsign_routes", current, staged)
    conn.execute("DELETE FROM ref.callsign_routes")
    conn.execute(
        "INSERT INTO ref.callsign_routes"
        " (callsign, destination, n_flights, share, last_seen, source)"
        " SELECT callsign, destination, n_flights, share, last_seen, source FROM stage_routes"
    )
    return int(staged)


class RoutesWindow(Config):
    """The explicit `[window_start, window_end)` of flight-list `first_seen` (ISO 8601)."""

    window_start: str
    window_end: str


@op
def routes_refresh_op(context: OpExecutionContext, config: RoutesWindow) -> None:
    start = datetime.fromisoformat(config.window_start)
    end = datetime.fromisoformat(config.window_end)
    settings = JobsSettings()
    with recorded_run(settings, "routes_refresh", start, end) as run:
        run.rows_out = rebuild(run.conn, start, end)
    context.log.info(f"{run.rows_out} routes")


@job(description="Rebuild ref.callsign_routes from the last 28 days of OpenSky flight lists.")
def routes_refresh() -> None:
    routes_refresh_op()


def window_for_tick(tick: datetime) -> tuple[datetime, datetime]:
    """The 28 days before the tick's UTC day."""
    end = datetime.combine(tick.astimezone(UTC).date(), time(), UTC)
    return end - LOOKBACK, end


@schedule(
    job=routes_refresh,
    cron_schedule="30 8 * * *",
    execution_timezone="UTC",
    default_status=DefaultScheduleStatus.RUNNING,
)
def routes_refresh_schedule(context: ScheduleEvaluationContext) -> RunRequest:
    tick = context.scheduled_execution_time or datetime.now(UTC)
    start, end = window_for_tick(tick)
    window = {"window_start": start.isoformat(), "window_end": end.isoformat()}
    return RunRequest(
        run_key=window["window_end"],
        run_config={"ops": {"routes_refresh_op": {"config": window}}},
    )
