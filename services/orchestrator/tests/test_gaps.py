from datetime import UTC, datetime, timedelta

from orchestrator.gaps import find_gaps, slot_of

T0 = datetime(2026, 11, 13, 16, 0, tzinfo=UTC)  # on the 90 s grid


def slots(*indexes: int) -> set[datetime]:
    return {T0 + timedelta(seconds=90 * i) for i in indexes}


def at(i: int) -> datetime:
    return T0 + timedelta(seconds=90 * i)


def test_requests_map_to_the_slot_they_started_in() -> None:
    assert slot_of(T0 + timedelta(seconds=43), offset_s=0) == T0
    assert slot_of(T0 + timedelta(seconds=89.9), offset_s=0) == T0
    assert slot_of(T0 + timedelta(seconds=90), offset_s=0) == at(1)
    assert slot_of(T0 + timedelta(seconds=50), offset_s=45) == T0 + timedelta(seconds=45)


def test_three_missed_slots_are_not_a_gap() -> None:
    ok = slots(0, 1, 5, 6)  # 2, 3, 4 missing
    assert find_gaps(ok, last_ok_before=None, start=at(0), end=at(7)) == []


def test_four_missed_slots_are_one_gap_at_the_first_missed_slot() -> None:
    ok = slots(0, 1, 6, 7)  # 2..5 missing
    assert find_gaps(ok, last_ok_before=None, start=at(0), end=at(8)) == [at(2)]


def test_each_separate_run_is_its_own_gap() -> None:
    ok = slots(0, 5, 10)
    assert find_gaps(ok, last_ok_before=None, start=at(0), end=at(11)) == [at(1), at(6)]


def test_a_gap_still_open_at_the_window_end_is_reported() -> None:
    assert find_gaps(slots(0), last_ok_before=None, start=at(0), end=at(5)) == [at(1)]


def test_a_gap_that_began_before_the_window_keeps_its_real_start() -> None:
    # The last success was long before the window, so every run reports the same gap start
    # (and the same dedupe key) instead of a new gap at each window start.
    before = at(-1000)
    assert find_gaps(set(), last_ok_before=before, start=at(0), end=at(10)) == [at(-999)]


def test_a_short_miss_across_the_window_start_counts_the_slots_before_it() -> None:
    # Slots -2 and -1 were missed before the window, 0 and 1 inside: four in a row.
    assert find_gaps(slots(2), last_ok_before=at(-3), start=at(0), end=at(3)) == [at(-2)]


def test_a_collector_that_never_succeeded_has_no_gap() -> None:
    # Otherwise each 5-minute window would start a "new" gap with a new dedupe key.
    assert find_gaps(set(), last_ok_before=None, start=at(0), end=at(10)) == []


def test_misses_before_a_collectors_first_success_are_not_a_gap() -> None:
    assert find_gaps(slots(5), last_ok_before=None, start=at(0), end=at(6)) == []


def test_a_window_starting_off_the_grid_begins_at_the_next_slot() -> None:
    ok = slots(1, 2, 3, 4)
    assert find_gaps(ok, last_ok_before=at(0), start=at(0) + timedelta(seconds=1), end=at(5)) == []


def test_scheduled_window_is_two_hours_ending_five_minutes_before_the_tick() -> None:
    from orchestrator.gaps import window_for_tick

    tick = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
    assert window_for_tick(tick) == (
        datetime(2026, 11, 16, 9, 55, tzinfo=UTC),
        datetime(2026, 11, 16, 11, 55, tzinfo=UTC),
    )
