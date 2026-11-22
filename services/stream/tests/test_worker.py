from dataclasses import replace
from datetime import UTC, datetime, timedelta

from stream.rules import Airport, Event, Observation
from stream.worker import detect, process_pending

T0 = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
SLOT = timedelta(seconds=90)
LOWW = Airport("LOWW", 48.110298, 16.5697, 183.0)


def obs(i: int, **kw: object) -> Observation:
    base = Observation(
        snapshot_time=T0 + i * SLOT,
        time_position=T0 + i * SLOT,
        lat=47.5,
        lon=19.0,
        baro_altitude_m=9000.0,
        geo_altitude_m=None,
        vertical_rate_ms=0.0,
        on_ground=False,
        squawk="7700",
        callsign="WZZ123",
        h3_r4=None,
    )
    return replace(base, **kw)  # type: ignore[arg-type]


class FakeStore:
    """In-memory stand-in for `stream.store.Store`: aircraft -> observations, oldest first."""

    def __init__(self, tracks: dict[str, list[Observation]], last: datetime) -> None:
        self.tracks = tracks
        self.last = last
        self.events: dict[str, Event] = {}
        self.committed: list[datetime] = []

    def pending_snapshots(self, live_from: datetime) -> list[datetime]:
        times = {o.snapshot_time for track in self.tracks.values() for o in track}
        return sorted(t for t in times if t > self.last and t >= live_from)

    def target_airports(self) -> list[Airport]:
        return [LOWW]

    def at(self, t: datetime) -> list[tuple[str, Observation]]:
        return [(a, o) for a, track in self.tracks.items() for o in track if o.snapshot_time == t]

    def squawk_candidates(self, t: datetime) -> list[tuple[str, Observation]]:
        return [(a, o) for a, o in self.at(t) if o.squawk in {"7500", "7600", "7700"}]

    def squawk_history(self, icao24: str, code: str, t: datetime) -> list[Observation]:
        return [o for o in self.tracks[icao24] if o.squawk == code and o.snapshot_time <= t
                and o.snapshot_time > t - timedelta(hours=12)]  # fmt: skip

    def climb_candidates(self, t: datetime) -> list[tuple[str, Observation]]:
        return [(a, o) for a, o in self.at(t) if (o.vertical_rate_ms or 0) > 2]

    def previous_observations(self, icao24: str, t: datetime) -> list[Observation]:
        return [o for o in self.tracks[icao24] if o.snapshot_time < t][-3:]

    def qnh(self, station: str, at: datetime) -> float | None:
        return None

    def commit_snapshot(self, t: datetime, events: list[Event]) -> int:
        new = [e for e in events if e.dedupe_key not in self.events]
        self.events.update({e.dedupe_key: e for e in new})
        self.last = t
        self.committed.append(t)
        return len(new)


def test_snapshots_are_processed_in_order_and_progress_is_kept() -> None:
    store = FakeStore({"47a1b2": [obs(i) for i in range(5)]}, last=T0 - SLOT)
    assert process_pending(store, now=obs(4).snapshot_time) == 5
    assert store.committed == [obs(i).snapshot_time for i in range(5)]
    # One episode, one event, written when the third observation arrived.
    assert list(store.events) == ["squawk_7700:47a1b2:2026-11-22T12:00:00Z"]
    # Nothing new: a second run does nothing.
    assert process_pending(store, now=obs(4).snapshot_time) == 0


def test_snapshots_outside_the_live_window_are_skipped() -> None:
    store = FakeStore({"47a1b2": [obs(i) for i in range(10)]}, last=T0 - SLOT)
    now = obs(9).snapshot_time + timedelta(seconds=30)
    process_pending(store, now=now)
    # Live: snapshot_time >= now - 600 s, so obs(3) at 12:04:30 (now 12:14:00) is the first.
    assert store.committed[0] == obs(3).snapshot_time


def test_detect_finds_go_arounds_near_target_airports() -> None:
    near = {"lat": 48.13, "lon": 16.60, "baro_altitude_m": 400.0, "squawk": "1000"}
    track = [obs(0, vertical_rate_ms=-4.0, **near), obs(1, vertical_rate_ms=6.0, **near)]
    store = FakeStore({"440abc": track}, last=T0)
    events = detect(store, obs(1).snapshot_time, [LOWW])
    assert [e.kind for e in events] == ["go_around"]
