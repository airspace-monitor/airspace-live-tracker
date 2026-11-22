"""PostgreSQL access for the stream-worker, as the `stream_worker` role.

The connection is in autocommit mode, so reads never leave a transaction open while the worker
waits for notifications; `commit_snapshot` writes the events and the progress in one transaction.
Every raw query bounds `snapshot_time` with a parameter, so TimescaleDB only opens the chunks
it needs.
"""

from datetime import datetime, timedelta
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from stream.rules import (
    CLIMBING_MS,
    EMERGENCY_SQUAWKS,
    EUROPE_BOX,
    GO_AROUND_LOOKBACK,
    PREVIOUS_OBSERVATIONS,
    SQUAWK_LOOKBACK,
    Airport,
    Event,
    Observation,
)

COLUMNS = (
    "snapshot_time, time_position, lat, lon, baro_altitude_m, geo_altitude_m, vertical_rate_ms,"
    " on_ground, squawk, callsign, h3_r4"
)
# Coarse boxes around each target airport for the SQL filter; rules.nearest_airport checks the
# exact 15 km radius. 0.2 deg of latitude is 22 km; 0.3 deg of longitude is 20 km at 48 deg N.
BOX_LAT_DEG = 0.2
BOX_LON_DEG = 0.3
METAR_MAX_AGE = timedelta(minutes=90)

QUALIFYING_SQUAWK = """
  on_ground IS FALSE
  AND lat BETWEEN %(lat_min)s AND %(lat_max)s AND lon BETWEEN %(lon_min)s AND %(lon_max)s
"""

INSERT_EVENT = """
INSERT INTO core.events
  (dedupe_key, ts, kind, severity, lon, lat, icao24, callsign, airport_icao, h3_r4, title, payload)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (dedupe_key) DO NOTHING
"""


def _observation(row: tuple[Any, ...]) -> Observation:
    return Observation(*row)


def _box() -> dict[str, float]:
    lat_min, lat_max, lon_min, lon_max = EUROPE_BOX
    return {"lat_min": lat_min, "lat_max": lat_max, "lon_min": lon_min, "lon_max": lon_max}


class PgStore:
    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self.conn = conn
        self._airports: list[Airport] = []

    def pending_snapshots(self, live_from: datetime) -> list[datetime]:
        rows = self.conn.execute(
            """
            SELECT DISTINCT v.snapshot_time
            FROM raw.state_vectors v, ops.stream_state s
            WHERE v.snapshot_time >= %s AND v.snapshot_time > s.last_snapshot_time
            ORDER BY 1
            """,
            (live_from,),
        ).fetchall()
        return [r[0] for r in rows]

    def target_airports(self) -> list[Airport]:
        rows = self.conn.execute(
            "SELECT icao, lat, lon, elevation_m FROM ref.airports WHERE is_target ORDER BY icao"
        ).fetchall()
        self._airports = [Airport(*r) for r in rows]
        return self._airports

    def squawk_candidates(self, t: datetime) -> list[tuple[str, Observation]]:
        rows = self.conn.execute(
            f"""
            SELECT icao24, {COLUMNS} FROM raw.state_vectors
            WHERE snapshot_time = %(t)s AND squawk = ANY(%(codes)s) AND {QUALIFYING_SQUAWK}
            """,
            {"t": t, "codes": list(EMERGENCY_SQUAWKS), **_box()},
        ).fetchall()
        return [(r[0], _observation(r[1:])) for r in rows]

    def squawk_history(self, icao24: str, code: str, t: datetime) -> list[Observation]:
        rows = self.conn.execute(
            f"""
            SELECT {COLUMNS} FROM raw.state_vectors
            WHERE icao24 = %(icao24)s AND snapshot_time > %(start)s AND snapshot_time <= %(t)s
              AND squawk = %(code)s AND {QUALIFYING_SQUAWK}
            ORDER BY snapshot_time
            """,
            {"icao24": icao24, "code": code, "start": t - SQUAWK_LOOKBACK, "t": t, **_box()},
        ).fetchall()
        return [_observation(r) for r in rows]

    def climb_candidates(self, t: datetime) -> list[tuple[str, Observation]]:
        airports = self._airports or self.target_airports()
        if not airports:
            return []
        boxes = " OR ".join(
            f"(lat BETWEEN %(lat{i})s - {BOX_LAT_DEG} AND %(lat{i})s + {BOX_LAT_DEG}"
            f" AND lon BETWEEN %(lon{i})s - {BOX_LON_DEG} AND %(lon{i})s + {BOX_LON_DEG})"
            for i in range(len(airports))
        )
        params: dict[str, Any] = {"t": t, "climb": CLIMBING_MS}
        for i, a in enumerate(airports):
            params[f"lat{i}"], params[f"lon{i}"] = a.lat, a.lon
        rows = self.conn.execute(
            f"""
            SELECT icao24, {COLUMNS} FROM raw.state_vectors
            WHERE snapshot_time = %(t)s AND vertical_rate_ms > %(climb)s
              AND on_ground IS NOT TRUE AND ({boxes})
            """,
            params,
        ).fetchall()
        return [(r[0], _observation(r[1:])) for r in rows]

    def previous_observations(self, icao24: str, t: datetime) -> list[Observation]:
        rows = self.conn.execute(
            f"""
            SELECT {COLUMNS} FROM raw.state_vectors
            WHERE icao24 = %s AND snapshot_time < %s AND snapshot_time >= %s
            ORDER BY snapshot_time DESC LIMIT %s
            """,
            (icao24, t, t - GO_AROUND_LOOKBACK, PREVIOUS_OBSERVATIONS),
        ).fetchall()
        return [_observation(r) for r in reversed(rows)]

    def qnh(self, station: str, at: datetime) -> float | None:
        row = self.conn.execute(
            """
            SELECT qnh_hpa FROM core.metar
            WHERE station = %s AND observed_at <= %s AND observed_at > %s AND qnh_hpa IS NOT NULL
            ORDER BY observed_at DESC LIMIT 1
            """,
            (station, at, at - METAR_MAX_AGE),
        ).fetchone()
        return None if row is None else float(row[0])

    def commit_snapshot(self, t: datetime, events: list[Event]) -> int:
        new = 0
        with self.conn.transaction():
            for e in events:
                cur = self.conn.execute(
                    INSERT_EVENT,
                    (e.dedupe_key, e.ts, e.kind, e.severity, e.lon, e.lat, e.icao24, e.callsign,
                     e.airport_icao, e.h3_r4, e.title, Jsonb(e.payload)),
                )  # fmt: skip
                new += cur.rowcount
            self.conn.execute("UPDATE ops.stream_state SET last_snapshot_time = %s", (t,))
        return new
