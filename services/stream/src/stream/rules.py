"""Event detection rules (docs/04-pipelines.md#p3--stream-worker). Pure functions, no database.

Squawk: an episode is consecutive qualifying observations of one aircraft with one emergency code,
gaps <= 30 min. Qualifying: airborne, with a position, inside the Europe box (D14). An episode
becomes an event once it has 3 observations; `ts`, key and location come from its first.

Go-around: near a target airport and low, a descending observation followed within 3
observations by a climbing one, with no ground contact and no earlier climb in between.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from airspace_common.altitude import distance_km, height_above_airport_m
from airspace_common.timefmt import iso_z

EMERGENCY_SQUAWKS = {"7500": "unlawful interference", "7600": "radio failure", "7700": "emergency"}
# D14: lat_min, lat_max, lon_min, lon_max.
EUROPE_BOX = (35.0, 72.0, -25.0, 45.0)
EPISODE_GAP = timedelta(minutes=30)
MIN_EPISODE_OBSERVATIONS = 3
SQUAWK_LOOKBACK = timedelta(hours=12)

GO_AROUND_RADIUS_KM = 15.0
GO_AROUND_MAX_HEIGHT_M = 1000.0
DESCENDING_MS = -2.0
CLIMBING_MS = 2.0
PREVIOUS_OBSERVATIONS = 3
GO_AROUND_LOOKBACK = timedelta(minutes=30)


@dataclass(frozen=True)
class Observation:
    """One aircraft's row in one snapshot (`raw.state_vectors`)."""

    snapshot_time: datetime
    time_position: datetime | None
    lat: float | None
    lon: float | None
    baro_altitude_m: float | None
    geo_altitude_m: float | None
    vertical_rate_ms: float | None
    on_ground: bool | None
    squawk: str | None
    callsign: str | None
    h3_r4: int | None


@dataclass(frozen=True)
class Airport:
    icao: str
    lat: float
    lon: float
    elevation_m: float


@dataclass(frozen=True)
class Event:
    """A `core.events` row."""

    dedupe_key: str
    ts: datetime
    kind: str
    severity: str
    lat: float | None
    lon: float | None
    icao24: str
    callsign: str | None
    airport_icao: str | None
    h3_r4: int | None
    title: str
    payload: dict[str, Any] = field(default_factory=dict)


def in_europe(lat: float, lon: float) -> bool:
    lat_min, lat_max, lon_min, lon_max = EUROPE_BOX
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


def qualifies_for_squawk(o: Observation, code: str) -> bool:
    return (
        o.squawk == code
        and o.on_ground is False
        and o.lat is not None
        and o.lon is not None
        and in_europe(o.lat, o.lon)
    )


def squawk_episode(
    history: Sequence[Observation], now: datetime, lookback: timedelta = SQUAWK_LOOKBACK
) -> list[Observation] | None:
    """The episode that ends with the last of `history`, if it has become an event.

    `history`: one aircraft's qualifying observations for one code with `snapshot_time` in
    `(now - lookback, now]`, oldest first. None when the episode is too short, or when it reaches
    back to the edge of the window: then it may have started earlier, and its event (with the
    earlier start in its key) was written when it was younger.
    """
    if not history:
        return None
    episode = [history[-1]]
    for o in reversed(history[:-1]):
        if episode[0].snapshot_time - o.snapshot_time > EPISODE_GAP:
            break
        episode.insert(0, o)
    if len(episode) < MIN_EPISODE_OBSERVATIONS:
        return None
    if episode[0].snapshot_time - (now - lookback) <= EPISODE_GAP:
        return None
    return episode


def _callsign(observations: Sequence[Observation]) -> str | None:
    return next((o.callsign for o in observations if o.callsign), None)


def squawk_event(icao24: str, code: str, episode: Sequence[Observation]) -> Event:
    first = episode[0]
    kind = f"squawk_{code}"
    callsign = _callsign(episode)
    return Event(
        dedupe_key=f"{kind}:{icao24}:{iso_z(first.snapshot_time, 'seconds')}",
        ts=first.snapshot_time,
        kind=kind,
        severity="alert",
        lat=first.lat,
        lon=first.lon,
        icao24=icao24,
        callsign=callsign,
        airport_icao=None,
        h3_r4=first.h3_r4,
        title=f"Squawk {code} {EMERGENCY_SQUAWKS[code]} ({callsign or icao24})",
        payload={
            "squawk": code,
            "observations": len(episode),
            "baro_altitude_m": first.baro_altitude_m,
        },
    )


def nearest_airport(o: Observation, airports: Sequence[Airport]) -> tuple[Airport, float] | None:
    """The nearest target airport within the go-around radius, with its distance in km."""
    if o.lat is None or o.lon is None:
        return None
    best: tuple[Airport, float] | None = None
    for a in airports:
        d = distance_km(o.lat, o.lon, a.lat, a.lon)
        if d <= GO_AROUND_RADIUS_KM and (best is None or d < best[1]):
            best = (a, d)
    return best


def _height(o: Observation, airport: Airport, qnh_hpa: float | None) -> tuple[float, str] | None:
    return height_above_airport_m(o.baro_altitude_m, o.geo_altitude_m, airport.elevation_m, qnh_hpa)


def _low_and_near(o: Observation, airport: Airport, qnh_hpa: float | None) -> bool:
    if o.on_ground or o.lat is None or o.lon is None:
        return False
    if distance_km(o.lat, o.lon, airport.lat, airport.lon) > GO_AROUND_RADIUS_KM:
        return False
    height = _height(o, airport, qnh_hpa)
    return height is not None and height[0] < GO_AROUND_MAX_HEIGHT_M


def go_around_event(
    icao24: str,
    current: Observation,
    previous: Sequence[Observation],
    airport: Airport,
    qnh_hpa: float | None,
) -> Event | None:
    """A go-around whose climbing observation is `current`.

    `previous`: up to the aircraft's 3 observations before `current` (within 30 min), oldest
    first. `qnh_hpa`: the airport's METAR QNH from the 90 min before `current`, if any.
    """
    vr = current.vertical_rate_ms
    if current.time_position is None or vr is None or vr <= CLIMBING_MS:
        return None
    recent = list(previous)[-PREVIOUS_OBSERVATIONS:]
    descents = [
        i
        for i, o in enumerate(recent)
        if o.vertical_rate_ms is not None and o.vertical_rate_ms < DESCENDING_MS
    ]
    if not descents:
        return None
    descent = recent[descents[-1]]
    between = recent[descents[-1] + 1 :]
    if any(o.vertical_rate_ms is not None and o.vertical_rate_ms > CLIMBING_MS for o in between):
        return None  # the climb started earlier; that observation was the go-around
    if not all(_low_and_near(o, airport, qnh_hpa) for o in [descent, *between, current]):
        return None
    height = _height(current, airport, qnh_hpa)
    assert height is not None and current.lat is not None and current.lon is not None
    callsign = current.callsign or _callsign(list(reversed(recent)))
    return Event(
        dedupe_key=f"go_around:{icao24}:{iso_z(current.time_position, 'seconds')}",
        ts=current.time_position,
        kind="go_around",
        severity="warn",
        lat=current.lat,
        lon=current.lon,
        icao24=icao24,
        callsign=callsign,
        airport_icao=airport.icao,
        h3_r4=current.h3_r4,
        title=f"Go-around at {airport.icao} ({callsign or icao24})",
        payload={
            "height_m": round(height[0]),
            "height_method": height[1],
            "descent_vertical_rate_ms": descent.vertical_rate_ms,
            "climb_vertical_rate_ms": vr,
            "distance_km": round(
                distance_km(current.lat, current.lon, airport.lat, airport.lon), 1
            ),
        },
    )
