from datetime import UTC, datetime

from orchestrator.routes import window_for_tick


def test_the_window_is_the_28_utc_days_before_the_tick() -> None:
    assert window_for_tick(datetime(2026, 11, 26, 8, 30, tzinfo=UTC)) == (
        datetime(2026, 10, 29, tzinfo=UTC),
        datetime(2026, 11, 26, tzinfo=UTC),
    )


def test_a_tick_with_another_offset_uses_its_utc_day() -> None:
    from datetime import timedelta, timezone

    tick = datetime(2026, 11, 26, 0, 30, tzinfo=timezone(timedelta(hours=2)))  # 25th 22:30 UTC
    assert window_for_tick(tick)[1] == datetime(2026, 11, 25, tzinfo=UTC)
