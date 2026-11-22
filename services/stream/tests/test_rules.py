from dataclasses import replace
from datetime import UTC, datetime, timedelta

from stream.rules import (
    Airport,
    Observation,
    go_around_event,
    nearest_airport,
    qualifies_for_squawk,
    squawk_episode,
    squawk_event,
)

T0 = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
SLOT = timedelta(seconds=90)
LOWW = Airport("LOWW", 48.110298, 16.5697, 183.0)
LZIB = Airport("LZIB", 48.1702, 17.2127, 133.0)


def obs(i: int, **kw: object) -> Observation:
    """The i-th observation on the 90 s grid: airborne over Hungary, squawking 7700."""
    base = Observation(
        snapshot_time=T0 + i * SLOT,
        time_position=T0 + i * SLOT - timedelta(seconds=2),
        lat=47.5,
        lon=19.0,
        baro_altitude_m=9000.0,
        geo_altitude_m=9100.0,
        vertical_rate_ms=0.0,
        on_ground=False,
        squawk="7700",
        callsign="WZZ123",
        h3_r4=595183493020581887,
    )
    return replace(base, **kw)  # type: ignore[arg-type]


# --- squawk -------------------------------------------------------------------------------


def test_only_airborne_observations_with_a_position_in_europe_qualify() -> None:
    assert qualifies_for_squawk(obs(0), "7700")
    assert not qualifies_for_squawk(obs(0), "7600")
    assert not qualifies_for_squawk(obs(0, on_ground=True), "7700")
    assert not qualifies_for_squawk(obs(0, on_ground=None), "7700")
    assert not qualifies_for_squawk(obs(0, lat=None, lon=None), "7700")
    assert not qualifies_for_squawk(obs(0, lat=34.0), "7700")  # south of the box
    assert not qualifies_for_squawk(obs(0, lon=46.0), "7700")  # east of the box


def test_an_episode_needs_three_observations() -> None:
    now = obs(1).snapshot_time
    assert squawk_episode([obs(0), obs(1)], now) is None
    now = obs(2).snapshot_time
    assert squawk_episode([obs(0), obs(1), obs(2)], now) == [obs(0), obs(1), obs(2)]


def test_a_gap_over_30_minutes_starts_a_new_episode() -> None:
    late = obs(30)  # 45 min after obs(1)
    history = [obs(0), obs(1), late, obs(31), obs(32)]
    assert squawk_episode(history, obs(32).snapshot_time) == [late, obs(31), obs(32)]
    # Within 30 min the episode continues and keeps its first observation.
    history = [obs(0), obs(1), obs(20), obs(21)]
    episode = squawk_episode(history, obs(21).snapshot_time)
    assert episode is not None and episode[0] == obs(0)


def test_an_episode_reaching_the_lookback_edge_is_skipped() -> None:
    # Its start may lie before the window, so its key could differ from the one already written.
    now = obs(10).snapshot_time
    history = [obs(1), obs(2), obs(10)]
    assert squawk_episode(history, now, lookback=timedelta(minutes=20)) is None
    assert squawk_episode(history, now, lookback=timedelta(hours=12)) is not None


def test_squawk_event_uses_the_first_observation() -> None:
    episode = [obs(0, callsign=None), obs(1), obs(2)]
    event = squawk_event("47a1b2", "7700", episode)
    assert event.kind == "squawk_7700"
    assert event.severity == "alert"
    assert event.dedupe_key == "squawk_7700:47a1b2:2026-11-22T12:00:00Z"
    assert event.ts == T0
    assert (event.lat, event.lon) == (47.5, 19.0)
    assert event.callsign == "WZZ123"  # the first known callsign of the episode
    assert event.title == "Squawk 7700 emergency (WZZ123)"
    assert event.payload["observations"] == 3


def test_squawk_title_falls_back_to_icao24() -> None:
    episode = [obs(i, callsign=None, squawk="7600") for i in range(3)]
    assert squawk_event("47a1b2", "7600", episode).title == "Squawk 7600 radio failure (47a1b2)"


# --- go-around ----------------------------------------------------------------------------


def approach(i: int, vr: float, **kw: object) -> Observation:
    """Near LOWW, 400 m above pressure altitude 1013.25 hPa (217 m above the airport)."""
    near = {"lat": 48.13, "lon": 16.60, "baro_altitude_m": 400.0, "squawk": "1000"}
    return obs(i, vertical_rate_ms=vr, **{**near, **kw})


def test_nearest_target_airport_within_15_km() -> None:
    assert nearest_airport(approach(0, 0.0), [LZIB, LOWW]) == (LOWW, approach_distance())
    assert nearest_airport(obs(0), [LZIB, LOWW]) is None  # over Hungary, far from both


def approach_distance() -> float:
    from airspace_common.altitude import distance_km

    return distance_km(48.13, 16.60, LOWW.lat, LOWW.lon)


def test_descent_then_climb_is_a_go_around() -> None:
    previous = [approach(0, -4.0), approach(1, -3.0), approach(2, 0.5)]
    current = approach(3, 6.0, callsign="AUA478")
    event = go_around_event("440abc", current, previous, LOWW, qnh_hpa=None)
    assert event is not None
    assert event.kind == "go_around" and event.severity == "warn"
    assert event.ts == current.time_position
    assert event.dedupe_key == "go_around:440abc:2026-11-22T12:04:28Z"
    assert event.airport_icao == "LOWW"
    assert event.title == "Go-around at LOWW (AUA478)"
    assert event.payload["height_method"] == "uncorrected"
    assert event.payload["height_m"] == 217


def test_no_go_around_without_a_descent_in_the_previous_three() -> None:
    previous = [approach(0, -4.0), approach(1, 0.0), approach(2, 0.0), approach(3, 0.0)]
    assert go_around_event("440abc", approach(4, 6.0), previous[-3:], LOWW, None) is None


def test_no_go_around_when_the_current_observation_is_not_climbing() -> None:
    previous = [approach(0, -4.0)]
    assert go_around_event("440abc", approach(1, 2.0), previous, LOWW, None) is None


def test_a_long_climb_gives_one_event() -> None:
    # The second climbing observation has a climb between it and the descent.
    previous = [approach(0, -4.0), approach(1, 6.0)]
    assert go_around_event("440abc", approach(2, 7.0), previous, LOWW, None) is None


def test_touching_down_in_between_is_a_touch_and_go_not_a_go_around() -> None:
    previous = [approach(0, -4.0), approach(1, 0.0, on_ground=True)]
    assert go_around_event("440abc", approach(2, 6.0), previous, LOWW, None) is None


def test_too_high_or_too_far_is_not_a_go_around() -> None:
    previous = [approach(0, -4.0)]
    high = approach(1, 6.0, baro_altitude_m=1300.0)  # 1,117 m above LOWW
    assert go_around_event("440abc", high, previous, LOWW, None) is None
    far_descent = [approach(0, -4.0, lat=48.30)]  # about 21 km north
    assert go_around_event("440abc", approach(1, 6.0), far_descent, LOWW, None) is None


def test_qnh_from_the_metar_corrects_the_height() -> None:
    previous = [approach(0, -4.0)]
    event = go_around_event("440abc", approach(1, 6.0), previous, LOWW, qnh_hpa=1023.25)
    assert event is not None
    assert event.payload["height_method"] == "qnh"
    assert event.payload["height_m"] == 300  # 400 + 83 - 183


def test_no_height_means_no_go_around() -> None:
    previous = [approach(0, -4.0, baro_altitude_m=None, geo_altitude_m=None)]
    assert go_around_event("440abc", approach(1, 6.0), previous, LOWW, None) is None
