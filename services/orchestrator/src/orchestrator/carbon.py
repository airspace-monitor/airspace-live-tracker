"""`carbon_readings_record` (docs/04-pipelines.md#carbon_readings_record).

Every 5 minutes, asks carbon-signal for the intensity at the tick and stores it in
`ops.carbon_readings`. The window is the 5 minutes ending at the tick, and the reading is taken at
its end. A replayed window keeps the reading it first stored (`ON CONFLICT DO NOTHING`): it is
what the system saw at the time, including a demo override that may have ended since.
"""

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
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

STEP = timedelta(minutes=5)
TIMEOUT_S = 10

INSERT_SQL = """
INSERT INTO ops.carbon_readings (ts, intensity_g_kwh, source) VALUES (%s, %s, %s)
ON CONFLICT (ts) DO NOTHING
"""


@dataclass(frozen=True)
class Reading:
    ts: datetime
    intensity_g_kwh: float
    source: str


def fetch_reading(base_url: str, at: datetime) -> Reading:
    """GET /v1/intensity?at= from carbon-signal."""
    query = urllib.parse.urlencode({"at": at.astimezone(UTC).isoformat()})
    with urllib.request.urlopen(f"{base_url}/v1/intensity?{query}", timeout=TIMEOUT_S) as r:
        body = json.load(r)
    if body["source"] not in ("curve", "override"):
        raise ValueError(f"unexpected source {body['source']!r}")
    return Reading(at, float(body["intensity_g_kwh"]), body["source"])


def store_reading(conn: psycopg.Connection, reading: Reading) -> int:
    cur = conn.execute(INSERT_SQL, (reading.ts, reading.intensity_g_kwh, reading.source))
    return cur.rowcount


class CarbonWindow(Config):
    """The explicit `[window_start, window_end)` (ISO 8601 with a UTC offset)."""

    window_start: str
    window_end: str


@op
def carbon_readings_record_op(context: OpExecutionContext, config: CarbonWindow) -> None:
    start = datetime.fromisoformat(config.window_start)
    end = datetime.fromisoformat(config.window_end)
    settings = JobsSettings()
    with recorded_run(settings, "carbon_readings_record", start, end) as run:
        reading = fetch_reading(settings.carbon_signal_url, end)
        run.rows_out = store_reading(run.conn, reading)
    context.log.info(f"{reading.intensity_g_kwh} gCO2e/kWh ({reading.source}) at {end}")


@job(description="Store carbon-signal's intensity every 5 minutes (ADR-0006).")
def carbon_readings_record() -> None:
    carbon_readings_record_op()


def window_for_tick(tick: datetime) -> tuple[datetime, datetime]:
    return tick - STEP, tick


@schedule(
    job=carbon_readings_record,
    cron_schedule="*/5 * * * *",
    execution_timezone="UTC",
    default_status=DefaultScheduleStatus.RUNNING,
)
def carbon_readings_record_schedule(context: ScheduleEvaluationContext) -> RunRequest:
    tick = context.scheduled_execution_time or datetime.now(UTC)
    start, end = window_for_tick(tick.astimezone(UTC))
    window = {"window_start": start.isoformat(), "window_end": end.isoformat()}
    return RunRequest(
        run_key=window["window_end"],
        run_config={"ops": {"carbon_readings_record_op": {"config": window}}},
    )
