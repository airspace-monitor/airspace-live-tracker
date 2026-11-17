"""The Dagster code location `airspace`, served by the dagster-code container.

Jobs and schedules from docs/04-pipelines.md#p4--orchestrated-jobs are added here as each
milestone builds them.
"""

from dagster import Definitions

from orchestrator.aggregates import agg_backfill_refresh, agg_backfill_refresh_schedule
from orchestrator.backup import backup, backup_schedule
from orchestrator.gaps import collector_gap_check, collector_gap_check_schedule

defs = Definitions(
    jobs=[agg_backfill_refresh, backup, collector_gap_check],
    schedules=[agg_backfill_refresh_schedule, backup_schedule, collector_gap_check_schedule],
)
