"""Height above an airport and great-circle distance (docs/04-pipelines.md#shared-definitions).

Shared so the stream-worker, the sessionizer and model training compute them the same way.
"""

import math
from typing import Literal

HeightMethod = Literal["qnh", "uncorrected", "geo"]

# Metres of pressure altitude per hPa of QNH difference from the 1013.25 hPa standard.
METRES_PER_HPA = 8.3
STANDARD_HPA = 1013.25
EARTH_RADIUS_KM = 6371.0088


def height_above_airport_m(
    baro_altitude_m: float | None,
    geo_altitude_m: float | None,
    elevation_m: float,
    qnh_hpa: float | None = None,
) -> tuple[float, HeightMethod] | None:
    """Height above the airport and how it was found, or None when the state has no altitude.

    `qnh_hpa` is the airport's METAR QNH, only when it was observed within 90 min before the
    state; the caller looks it up.
    """
    if baro_altitude_m is not None:
        if qnh_hpa is not None:
            corrected = baro_altitude_m + METRES_PER_HPA * (qnh_hpa - STANDARD_HPA)
            return corrected - elevation_m, "qnh"
        return baro_altitude_m - elevation_m, "uncorrected"
    if geo_altitude_m is not None:
        return geo_altitude_m - elevation_m, "geo"
    return None


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle (haversine) distance."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))
