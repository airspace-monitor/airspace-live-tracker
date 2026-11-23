"""The simulated grid's carbon intensity (docs/adr/0006-carbon-aware-operations.md).

A synthetic Central European day in gCO₂e/kWh: lowest around midday (solar), highest in the early
evening. Each day gets its own offset (windy or calm days), and smooth noise is added. Every value
is a pure function of the timestamp and the seed, so the same instant always gives the same value.
"""

import hashlib
import math
from datetime import UTC, datetime, timedelta

MIN_G_KWH = 100.0
MAX_G_KWH = 480.0
NIGHT_G_KWH = 330.0
SOLAR_DIP_G_KWH = 170.0  # at about 12:30 local time
EVENING_PEAK_G_KWH = 90.0  # at about 18:30 local time
DAY_OFFSET_G_KWH = 40.0  # ± per day
NOISE_G_KWH = 15.0  # ± per noise step, interpolated in between
NOISE_STEP = timedelta(minutes=15)
UTC_TO_LOCAL_H = 1.0  # Central European standard time; the curve ignores summer time


def _unit(seed: int, *key: object) -> float:
    """A deterministic number in [-1, 1) for the given key."""
    digest = hashlib.sha256(repr((seed, *key)).encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**63 - 1


def _noise(seed: int, t: datetime) -> float:
    step = NOISE_STEP.total_seconds()
    pos = t.timestamp() / step
    i = math.floor(pos)
    frac = pos - i
    a, b = _unit(seed, "noise", i), _unit(seed, "noise", i + 1)
    return a + (b - a) * frac


def intensity(t: datetime, seed: int = 0) -> float:
    """gCO₂e/kWh of the simulated grid at `t` (timezone-aware), rounded to 0.1."""
    t = t.astimezone(UTC)
    hour = (t.hour + t.minute / 60 + t.second / 3600 + UTC_TO_LOCAL_H) % 24
    value = (
        NIGHT_G_KWH
        - SOLAR_DIP_G_KWH * math.exp(-(((hour - 12.5) / 3.0) ** 2))
        + EVENING_PEAK_G_KWH * math.exp(-(((hour - 18.5) / 2.0) ** 2))
        + DAY_OFFSET_G_KWH * _unit(seed, "day", t.date().isoformat())
        + NOISE_G_KWH * _noise(seed, t)
    )
    return round(min(MAX_G_KWH, max(MIN_G_KWH, value)), 1)


def simulated_time(t: datetime, epoch: datetime, scale: float) -> datetime:
    """The simulated clock: equal to `t` at `scale` 1, and `scale` times faster from `epoch`."""
    if scale == 1:
        return t
    return epoch + (t - epoch) * scale
