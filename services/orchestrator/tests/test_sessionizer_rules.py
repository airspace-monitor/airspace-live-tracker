import itertools
import uuid
from datetime import UTC, datetime, timedelta

from orchestrator.flights import Airport, Flight, Point, Sessionizer, uuid7

T0 = datetime(2026, 11, 25, 10, 0, tzinfo=UTC)
LOWW = Airport("LOWW", 48.110298, 16.5697, 182.88)
FAR = (50.0, 10.0)  # far from every target airport


def pt(
    minute: float,
    *,
    ground: bool = False,
    alt: float | None = 9000.0,
    at: tuple[float, float] = FAR,
    callsign: str | None = "AUA123",
) -> Point:
    t = T0 + timedelta(minutes=minute)
    return Point(t, callsign, t, at[0], at[1], None if ground else alt, None, ground)


def engine(qnh: float | None = None) -> Sessionizer:
    ids = (uuid.UUID(int=i) for i in itertools.count(1))
    return Sessionizer([LOWW], lambda station, at: qnh, new_id=lambda: next(ids))


def run(points: list[Point], latest: Flight | None = None, context: Point | None = None):
    return engine().feed("440017", latest, context, points)


def test_airborne_points_form_one_active_flight() -> None:
    [f] = run([pt(0, alt=3000), pt(1.5, alt=9000), pt(3, alt=8000)])
    assert (f.status, f.n_points, f.first_seen, f.last_seen) == ("active", 3, T0, pt(3).t)
    assert f.max_alt_m == 9000
    assert f.callsign == "AUA123"


def test_ground_points_without_an_open_flight_never_become_a_flight() -> None:
    assert run([pt(0, ground=True), pt(1.5, ground=True), pt(3, ground=True)]) == []


def test_a_gap_over_20_minutes_closes_the_flight_and_opens_another() -> None:
    first, second = run([pt(0), pt(1.5), pt(22)])
    assert (first.status, first.last_seen) == ("lost", pt(1.5).t)
    assert (second.status, second.first_seen) == ("active", pt(22).t)
    assert first.flight_id != second.flight_id


def test_exactly_20_minutes_is_not_a_gap() -> None:
    [f] = run([pt(0), pt(20)])
    assert f.n_points == 2


def test_landing_extends_the_flight_and_takeoff_starts_a_new_one() -> None:
    near = (48.11, 16.57)
    arrived, departed = run(
        [
            pt(0, alt=600, at=near),
            pt(1.5, ground=True, at=near),
            pt(3, ground=True, at=near),
            pt(30, ground=True, at=near),  # gap while parked: the next flight is not open yet
            pt(31.5, ground=True, at=near),
            pt(33, alt=200, at=near),
        ]
    )
    assert (arrived.status, arrived.n_points) == ("completed", 3)
    assert (arrived.arr_icao, arrived.arr_source, arrived.arrival_method) == (
        "LOWW",
        "observed",
        "on_ground",
    )
    assert arrived.arrived_at == pt(1.5).t
    assert (departed.dep_icao, departed.dep_source, departed.first_seen) == (
        "LOWW",
        "observed",
        pt(33).t,
    )


def test_a_takeoff_far_from_targets_has_no_departure() -> None:
    [f] = run([pt(0, ground=True), pt(1.5)])
    assert f.dep_icao is None


def test_a_takeoff_after_a_long_gap_has_no_departure() -> None:
    near = (48.11, 16.57)
    [f] = run([pt(0, ground=True, at=near), pt(25)])
    assert f.dep_icao is None


def test_a_new_callsign_splits_but_null_does_not() -> None:
    a, b = run([pt(0), pt(1.5, callsign=None), pt(3), pt(4.5, callsign="AUA9")])
    assert (a.n_points, a.callsign, a.status) == (3, "AUA123", "lost")
    assert (b.callsign, b.n_points) == ("AUA9", 1)


def test_a_flight_starting_without_callsign_takes_the_first_one() -> None:
    [f] = run([pt(0, callsign=None), pt(1.5, callsign="AUA1")])
    assert (f.callsign, f.n_points) == ("AUA1", 2)


def test_a_stored_active_flight_is_extended() -> None:
    stored = Flight(uuid7(), "440017", "AUA123", T0, pt(3).t, n_points=3, max_alt_m=5000)
    [f] = run([pt(4.5, alt=7000)], latest=stored, context=pt(3))
    assert (f.flight_id, f.n_points, f.first_seen, f.max_alt_m) == (stored.flight_id, 4, T0, 7000)
    assert stored.n_points == 3  # the input is not mutated


def test_a_stored_flight_on_the_ground_closes_at_takeoff() -> None:
    stored = Flight(uuid7(), "440017", "AUA123", T0, pt(3).t, n_points=3)
    closed, new = run([pt(4.5)], latest=stored, context=pt(3, ground=True))
    assert (closed.flight_id, closed.status) == (stored.flight_id, "completed")
    assert new.status == "active"


def test_a_closed_stored_flight_is_not_extended() -> None:
    stored = Flight(uuid7(), "440017", "AUA123", T0, pt(3).t, status="lost", n_points=3)
    [f] = run([pt(4.5)], latest=stored, context=pt(3))
    assert f.flight_id != stored.flight_id


def test_a_lost_flight_low_near_a_target_arrived_on_its_last_airborne_point() -> None:
    e = engine(qnh=1023.25)  # +83 m of correction
    f = Flight(uuid7(), "440017", "AUA123", T0, pt(10).t, n_points=5)
    last = pt(10, alt=350, at=(48.12, 16.58))  # 350 + 83 - 183 = 250 m above LOWW
    e.close(f, last)
    assert (f.status, f.arr_icao, f.arrival_method, f.height_method) == (
        "lost",
        "LOWW",
        "last_airborne",
        "qnh",
    )
    assert f.arrived_at == last.t


def test_a_lost_flight_too_high_has_no_arrival() -> None:
    f = Flight(uuid7(), "440017", "AUA123", T0, pt(10).t)
    engine().close(f, pt(10, alt=600, at=(48.12, 16.58)))  # 417 m above, no QNH
    assert (f.status, f.arr_icao) == ("lost", None)


def test_a_flight_whose_last_point_is_missing_closes_lost() -> None:
    f = Flight(uuid7(), "440017", "AUA123", T0, pt(10).t)
    engine().close(f, None)
    assert (f.status, f.arr_icao) == ("lost", None)


def test_time_position_is_the_arrival_time_when_present() -> None:
    near = (48.11, 16.57)
    p = pt(1.5, ground=True, at=near)
    earlier = Point(p.t, p.callsign, p.t - timedelta(seconds=40), *near, None, None, True)
    [f] = run([pt(0, alt=500, at=near), earlier])
    assert f.arrived_at == p.t - timedelta(seconds=40)


def test_uuid7_is_version_7_and_time_ordered() -> None:
    a, b = uuid7(), uuid7()
    assert a.version == 7 and a.variant == uuid.RFC_4122
    assert a.int >> 80 <= b.int >> 80
