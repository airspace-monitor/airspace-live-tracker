"""The Dagster code location `airspace`, served by the dagster-code container.

Jobs and schedules from docs/04-pipelines.md#p4--orchestrated-jobs are added here as each
milestone builds them.
"""

from dagster import Definitions

from orchestrator.aggregates import agg_backfill_refresh, agg_backfill_refresh_schedule
from orchestrator.backup import backup, backup_schedule
from orchestrator.carbon import carbon_readings_record, carbon_readings_record_schedule
from orchestrator.gaps import collector_gap_check, collector_gap_check_schedule

defs = Definitions(
    jobs=[agg_backfill_refresh, backup, carbon_readings_record, collector_gap_check],
    schedules=[
        agg_backfill_refresh_schedule,
        backup_schedule,
        carbon_readings_record_schedule,
        collector_gap_check_schedule,
    ],
)
