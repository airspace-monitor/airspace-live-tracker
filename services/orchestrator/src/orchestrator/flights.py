"""Flight sessions from state vectors (docs/04-pipelines.md#flights_sessionizer), without I/O.

`Sessionizer.feed` takes one aircraft's points in time order, with its latest stored flight, and
returns the flights it opened, extended or closed. The rules:

- A flight opens at an airborne point when the aircraft has no open flight ([D16]). Points on the
  ground with no open flight are only context: the one just before a takeoff sets the departure.
- A point extends the open flight unless it starts a boundary: a gap of more than 20 min since the
  flight's last point; a takeoff (the previous point on the ground, this one airborne); or a new
  non-NULL callsign different from the flight's (NULL never splits).
- A closed flight is `completed` when its last point is on the ground, otherwise `lost`.
- Observed arrival at a target airport A: the first point on the ground within 5 km of A
  (`on_ground`); or, when the flight closes `lost`, its last (airborne) point within 5 km of A and
  under 300 m above it (`last_airborne`). Observed departure: the point on the ground just before
  the flight's first point, within 5 km of a target airport.

[D16]: docs/11-tasks.md#decided-while-building
"""

import os
import time
import uuid
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta

from airspace_common.altitude import distance_km, height_above_airport_m

MAX_GAP = timedelta(minutes=20)
AIRPORT_RADIUS_KM = 5.0
LAST_AIRBORNE_MAX_HEIGHT_M = 300.0


def uuid7() -> uuid.UUID:
    """A UUIDv7 (RFC 9562): 48-bit Unix milliseconds, then random bits."""
    ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")
    value = (ms & ((1 << 48) - 1)) << 80 | rand & ((1 << 80) - 1)
    value = value & ~(0xF << 76) | 0x7 << 76  # version 7
    value = value & ~(0x3 << 62) | 0x2 << 62  # RFC 4122 variant
    return uuid.UUID(int=value)


@dataclass(frozen=True)
class Point:
    t: datetime  # snapshot_time
    callsign: str | None
    time_position: datetime | None
    lat: float | None
    lon: float | None
    baro_altitude_m: float | None
    geo_altitude_m: float | None
    on_ground: bool

    @property
    def when(self) -> datetime:
        """When the position was observed: `time_position`, or the snapshot time without one."""
        return self.time_position or self.t

    @property
    def altitude_m(self) -> float | None:
        return self.baro_altitude_m if self.baro_altitude_m is not None else self.geo_altitude_m


@dataclass(frozen=True)
class Airport:
    icao: str
    lat: float
    lon: float
    elevation_m: float


@dataclass
class Flight:
    flight_id: uuid.UUID
    icao24: str
    callsign: str | None
    first_seen: datetime
    last_seen: datetime
    status: str = "active"
    finalized: bool = False
    dep_icao: str | None = None
    dep_source: str | None = None
    arr_icao: str | None = None
    arr_source: str | None = None
    arrived_at: datetime | None = None
    arrival_method: str | None = None
    height_method: str | None = None
    max_alt_m: float | None = None
    n_points: int = 0
    changed: bool = field(default=False, compare=False)


# (station, at) → the QNH observed within 90 min before `at`, or None.
QnhLookup = Callable[[str, datetime], float | None]


def near_airport(p: Point, airports: Sequence[Airport]) -> Airport | None:
    if p.lat is None or p.lon is None:
        return None
    for a in airports:
        # A cheap box first: 5 km is under 0.05° of latitude and 0.08° of longitude here.
        if (
            abs(p.lat - a.lat) < 0.1
            and abs(p.lon - a.lon) < 0.2
            and distance_km(p.lat, p.lon, a.lat, a.lon) <= AIRPORT_RADIUS_KM
        ):
            return a
    return None


class Sessionizer:
    def __init__(
        self, airports: Sequence[Airport], qnh: QnhLookup, new_id: Callable[[], uuid.UUID] = uuid7
    ) -> None:
        self.airports = airports
        self.qnh = qnh
        self.new_id = new_id

    def feed(
        self,
        icao24: str,
        latest: Flight | None,
        context: Point | None,
        points: Iterable[Point],
    ) -> list[Flight]:
        """Processes `points` (time order, all after `latest.last_seen`). `latest` is the aircraft's
        most recent stored flight; `context` its last point before `points` (within the fetched
        range), used for the takeoff boundary and the departure. Returns the flights that
        changed."""
        out: dict[uuid.UUID, Flight] = {}
        current = replace(latest) if latest and latest.status == "active" else None
        prev = context
        for p in points:
            if current is not None and self._boundary(current, prev, p):
                self.close(current, prev)
                out[current.flight_id] = current
                current = None
            if current is None:
                if p.on_ground:
                    prev = p
                    continue
                current = self._open(icao24, p, prev)
            self._extend(current, p)
            out[current.flight_id] = current
            prev = p
        return list(out.values())

    @staticmethod
    def _boundary(f: Flight, prev: Point | None, p: Point) -> bool:
        if p.t - f.last_seen > MAX_GAP:
            return True
        if prev is not None and prev.t == f.last_seen and prev.on_ground and not p.on_ground:
            return True
        return p.callsign is not None and f.callsign is not None and p.callsign != f.callsign

    def _open(self, icao24: str, p: Point, prev: Point | None) -> Flight:
        f = Flight(self.new_id(), icao24, p.callsign, p.t, p.t, changed=True)
        if prev is not None and prev.on_ground and p.t - prev.t <= MAX_GAP:
            airport = near_airport(prev, self.airports)
            if airport is not None:
                f.dep_icao, f.dep_source = airport.icao, "observed"
        return f

    def _extend(self, f: Flight, p: Point) -> None:
        f.last_seen = p.t
        f.n_points += 1
        f.callsign = p.callsign or f.callsign
        if p.altitude_m is not None and not p.on_ground:
            f.max_alt_m = p.altitude_m if f.max_alt_m is None else max(f.max_alt_m, p.altitude_m)
        if p.on_ground and f.arr_icao is None:
            airport = near_airport(p, self.airports)
            if airport is not None:
                f.arr_icao, f.arr_source, f.arrived_at = airport.icao, "observed", p.when
                f.arrival_method = "on_ground"
        f.changed = True

    def close(self, f: Flight, last: Point | None) -> None:
        """Closes `f`; `last` is its last point (None if it can no longer be found)."""
        f.status = "completed" if last is not None and last.on_ground else "lost"
        f.changed = True
        if f.status != "lost" or f.arr_icao is not None or last is None:
            return
        airport = near_airport(last, self.airports)
        if airport is None:
            return
        height = height_above_airport_m(
            last.baro_altitude_m,
            last.geo_altitude_m,
            airport.elevation_m,
            self.qnh(airport.icao, last.when),
        )
        if height is not None and height[0] < LAST_AIRBORNE_MAX_HEIGHT_M:
            f.arr_icao, f.arr_source, f.arrived_at = airport.icao, "observed", last.when
            f.arrival_method, f.height_method = "last_airborne", height[1]
