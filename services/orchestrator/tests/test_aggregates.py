from datetime import UTC, datetime, timedelta

from orchestrator.aggregates import days_to_refresh, scheduled_window


def ts(day: int, hour: int = 12) -> datetime:
    return datetime(2026, 11, day, hour, tzinfo=UTC)


def test_no_late_snapshots_means_no_refresh() -> None:
    assert days_to_refresh([]) is None


def test_late_snapshots_refresh_whole_utc_days_from_earliest_to_latest() -> None:
    assert days_to_refresh([ts(14, 23), ts(13, 0), ts(13, 18)]) == (ts(13, 0), ts(15, 0))


def test_one_late_snapshot_refreshes_its_day() -> None:
    assert days_to_refresh([ts(10, 5)]) == (ts(10, 0), ts(11, 0))


def test_scheduled_window_starts_where_the_last_ok_run_ended() -> None:
    # Q7: a failed run in between must not leave late data unmaterialised.
    tick = ts(17, 10)
    assert scheduled_window(tick, last_ok_end=ts(17, 7)) == (ts(17, 7), tick)


def test_first_run_looks_back_65_minutes() -> None:
    tick = ts(17, 10)
    assert scheduled_window(tick, last_ok_end=None) == (tick - timedelta(minutes=65), tick)


def test_lookback_is_capped_at_7_days() -> None:
    tick = ts(17, 10)
    assert scheduled_window(tick, last_ok_end=ts(1)) == (tick - timedelta(days=7), tick)
