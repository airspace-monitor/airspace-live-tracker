from dagster import Definitions

from orchestrator.definitions import defs


def test_code_location_loads() -> None:
    assert isinstance(defs, Definitions)
    Definitions.validate_loadable(defs)


def test_every_schedule_starts_running() -> None:
    # Dagster schedules default to STOPPED, which would silently skip the nightly backup.
    from dagster import DefaultScheduleStatus

    schedules = list(defs.schedules or [])
    assert schedules
    for s in schedules:
        assert s.default_status == DefaultScheduleStatus.RUNNING, s.name
