from datetime import UTC, datetime, timedelta

from orchestrator.labels import Label, Labels, merge, nearest, window_for_tick

T0 = datetime(2026, 11, 24, 10, 0, tzinfo=UTC)
NONE = Labels(None, None, None, None)


def label(minutes: float, dep: str | None = "EDDF", arr: str | None = "LOWW") -> Label:
    return Label(T0 + timedelta(minutes=minutes), dep, arr)


def test_the_closest_candidate_wins() -> None:
    assert nearest(T0, [label(-20), label(4), label(-6)]) == label(4)


def test_candidates_more_than_30_min_away_are_ignored() -> None:
    assert nearest(T0, [label(-31), label(30.5)]) is None
    assert nearest(T0, [label(30)]) == label(30)


def test_a_tie_goes_to_the_earlier_candidate() -> None:
    assert nearest(T0, [label(5, arr="LZIB"), label(-5, arr="LHBP")]) == label(-5, arr="LHBP")


def test_no_candidates_means_no_label() -> None:
    assert nearest(T0, []) is None


def test_estimates_fill_empty_labels_with_source_opensky() -> None:
    assert merge(NONE, label(0)) == Labels("EDDF", "opensky", "LOWW", "opensky")


def test_observed_values_are_never_overwritten() -> None:
    current = Labels("LOWW", "observed", "LHBP", "observed")
    assert merge(current, label(0, dep="LOWK", arr="LHBC")) == current


def test_only_the_side_that_is_not_observed_changes() -> None:
    current = Labels(None, None, "LOWW", "observed")
    assert merge(current, label(0, arr="LOWG")) == Labels("EDDF", "opensky", "LOWW", "observed")


def test_a_null_estimate_keeps_the_current_value() -> None:
    current = Labels("EGLL", "opensky", None, None)
    assert merge(current, label(0, dep=None, arr=None)) == current


def test_a_newer_opensky_estimate_replaces_an_older_one() -> None:
    current = Labels("EGLL", "opensky", "LOWW", "opensky")
    assert merge(current, label(0, dep="EGKK")) == Labels("EGKK", "opensky", "LOWW", "opensky")


def test_the_window_is_the_utc_day_before_the_tick() -> None:
    assert window_for_tick(datetime(2026, 11, 25, 8, 0, tzinfo=UTC)) == (
        datetime(2026, 11, 24, tzinfo=UTC),
        datetime(2026, 11, 25, tzinfo=UTC),
    )
