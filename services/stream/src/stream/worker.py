"""The stream-worker loop (docs/04-pipelines.md#p3--stream-worker).

On every `new_snapshot` notification, on startup and reconnect, and at least every 60 s, it
processes every live snapshot newer than `ops.stream_state.last_snapshot_time`, oldest first.
Each snapshot's events and the new progress are committed together, and events are inserted with
`ON CONFLICT (dedupe_key) DO NOTHING`, so a crash or a rerun never duplicates or skips one.
"""

from datetime import datetime, timedelta
from typing import Protocol

import structlog

from airspace_common.live import LIVE_WINDOW_SECONDS
from stream.rules import (
    Airport,
    Event,
    Observation,
    go_around_event,
    nearest_airport,
    squawk_episode,
    squawk_event,
)

log = structlog.get_logger()


class Store(Protocol):
    def pending_snapshots(self, live_from: datetime) -> list[datetime]:
        """Snapshot times newer than the stored progress and at or after `live_from`."""
        ...

    def target_airports(self) -> list[Airport]: ...

    def squawk_candidates(self, t: datetime) -> list[tuple[str, Observation]]:
        """Qualifying emergency-squawk observations in snapshot `t` (rules.qualifies_for_squawk)."""
        ...

    def squawk_history(self, icao24: str, code: str, t: datetime) -> list[Observation]:
        """The aircraft's qualifying observations for `code` in `(t - 12 h, t]`, oldest first."""
        ...

    def climb_candidates(self, t: datetime) -> list[tuple[str, Observation]]:
        """Airborne observations in snapshot `t` climbing faster than +2 m/s near a target."""
        ...

    def previous_observations(self, icao24: str, t: datetime) -> list[Observation]:
        """The aircraft's last 3 observations before `t` (within 30 min), oldest first."""
        ...

    def qnh(self, station: str, at: datetime) -> float | None:
        """QNH of the station's latest METAR from the 90 min before `at`."""
        ...

    def commit_snapshot(self, t: datetime, events: list[Event]) -> int:
        """Inserts the events, sets the progress to `t`, commits. Returns how many were new."""
        ...


def detect(store: Store, t: datetime, airports: list[Airport]) -> list[Event]:
    events: list[Event] = []
    for icao24, o in store.squawk_candidates(t):
        assert o.squawk is not None
        episode = squawk_episode(store.squawk_history(icao24, o.squawk, t), now=t)
        if episode is not None:
            events.append(squawk_event(icao24, o.squawk, episode))
    for icao24, o in store.climb_candidates(t):
        near = nearest_airport(o, airports)
        if near is None:
            continue
        airport = near[0]
        previous = store.previous_observations(icao24, t)
        event = go_around_event(icao24, o, previous, airport, store.qnh(airport.icao, t))
        if event is not None:
            events.append(event)
    return events


def process_pending(store: Store, now: datetime) -> int:
    """Processes every pending live snapshot. Returns how many snapshots were processed."""
    live_from = now - timedelta(seconds=LIVE_WINDOW_SECONDS)
    pending = store.pending_snapshots(live_from)
    if not pending:
        return 0
    airports = store.target_airports()
    for t in pending:
        events = detect(store, t, airports)
        new = store.commit_snapshot(t, events)
        if events:
            log.info("events_detected", snapshot_time=t.isoformat(), detected=len(events),
                     new=new, keys=[e.dedupe_key for e in events])  # fmt: skip
    return len(pending)
