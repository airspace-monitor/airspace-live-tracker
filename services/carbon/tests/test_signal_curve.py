from datetime import UTC, datetime, timedelta

from carbon.curve import MAX_G_KWH, MIN_G_KWH, intensity, simulated_time

DAY = datetime(2026, 11, 24, tzinfo=UTC)


def at(hour: float, day: datetime = DAY) -> datetime:
    return day + timedelta(hours=hour)


def test_the_same_instant_always_gives_the_same_value() -> None:
    t = at(9.25)
    assert intensity(t, seed=1) == intensity(t, seed=1)


def test_another_seed_gives_another_curve() -> None:
    assert intensity(at(9.25), seed=1) != intensity(at(9.25), seed=2)


def test_midday_is_cleaner_than_the_evening_on_every_day() -> None:
    for d in range(30):
        day = DAY + timedelta(days=d)
        # 11:30 UTC is 12:30 local (solar minimum), 17:30 UTC is 18:30 local (evening peak).
        assert intensity(at(11.5, day)) < intensity(at(17.5, day)) - 100


def test_values_stay_in_range_over_a_year() -> None:
    values = [intensity(DAY + timedelta(minutes=37 * i)) for i in range(14_200)]
    assert min(values) >= MIN_G_KWH
    assert max(values) <= MAX_G_KWH
    # The curve really crosses the controller's green (< 200) and dirty (> 350) classes.
    assert min(values) < 200 < 350 < max(values)


def test_the_curve_is_smooth_between_minutes() -> None:
    values = [intensity(DAY + timedelta(minutes=m)) for m in range(24 * 60)]
    assert max(abs(b - a) for a, b in zip(values, values[1:], strict=False)) < 6


def test_the_simulated_clock_runs_faster_from_its_epoch() -> None:
    epoch = datetime(2026, 11, 23, tzinfo=UTC)
    assert simulated_time(epoch + timedelta(minutes=24), epoch, 60) == epoch + timedelta(days=1)
    t = datetime(2026, 11, 30, 8, tzinfo=UTC)
    assert simulated_time(t, epoch, 1) == t
