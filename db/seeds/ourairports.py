"""Seed `ref.airports` and `ref.runways` from OurAirports (docs/02-data-sources.md#reference-data).

Downloads both CSVs (public domain), or reads them from `--from-dir`, and upserts on the primary
keys, so it is safe to re-run. Connects as `jobs` (JOBS_PASSWORD, JOBS_DB_HOST). From M3,
`ref_refresh` takes over. On the VM:

    docker compose run --rm -v ../db:/db:ro dagster-code python /db/seeds/ourairports.py

Rows that are skipped (Q4, decided 2026-11-17):
- airports without an ICAO code, or without an elevation (`elevation_m` is required; a guessed 0
  would give wrong heights above the airport);
- closed runways, runways without an `le_ident`, and runways of airports that were skipped;
- a repeated `(airport, le_ident)`: the longest runway is kept.
"""

import argparse
import io
import sys
import urllib.request
from pathlib import Path
from typing import TextIO

from orchestrator.refdata.ourairports import (
    BASE_URL,
    TARGET_AIRPORTS,
    parse_airports,
    parse_runways,
)

UPSERT_AIRPORT = """
INSERT INTO ref.airports (icao, iata, name, type, lat, lon, elevation_m, country, is_target, geom)
VALUES (%(icao)s, %(iata)s, %(name)s, %(type)s, %(lat)s, %(lon)s, %(elevation_m)s, %(country)s,
        %(is_target)s, ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography)
ON CONFLICT (icao) DO UPDATE SET
  iata = EXCLUDED.iata, name = EXCLUDED.name, type = EXCLUDED.type, lat = EXCLUDED.lat,
  lon = EXCLUDED.lon, elevation_m = EXCLUDED.elevation_m, country = EXCLUDED.country,
  is_target = EXCLUDED.is_target, geom = EXCLUDED.geom
"""
UPSERT_RUNWAY = """
INSERT INTO ref.runways (airport_icao, le_ident, he_ident, le_heading_deg, he_heading_deg, length_m)
VALUES (%(airport_icao)s, %(le_ident)s, %(he_ident)s, %(le_heading_deg)s, %(he_heading_deg)s,
        %(length_m)s)
ON CONFLICT (airport_icao, le_ident) DO UPDATE SET
  he_ident = EXCLUDED.he_ident, le_heading_deg = EXCLUDED.le_heading_deg,
  he_heading_deg = EXCLUDED.he_heading_deg, length_m = EXCLUDED.length_m
"""


def _read(name: str, from_dir: Path | None) -> TextIO:
    if from_dir is not None:
        return (from_dir / name).open(encoding="utf-8", newline="")
    with urllib.request.urlopen(BASE_URL + name, timeout=120) as response:
        return io.StringIO(response.read().decode("utf-8"), newline="")


def load(from_dir: Path | None) -> tuple[int, int]:
    import psycopg

    from airspace_common.settings import JobsSettings

    with _read("airports.csv", from_dir) as f:
        airports = list(parse_airports(f))
    ids_to_icao = {a.pop("_id"): a["icao"] for a in airports}
    with _read("runways.csv", from_dir) as f:
        runways = list(parse_runways(f, ids_to_icao.values(), ids_to_icao))
    missing = TARGET_AIRPORTS - {a["icao"] for a in airports}
    if missing:
        raise SystemExit(f"target airports missing from OurAirports: {sorted(missing)}")

    settings = JobsSettings()
    with (
        psycopg.connect(
            host=settings.jobs_db_host,
            user="jobs",
            dbname="airspace",
            password=settings.jobs_password.get_secret_value(),
        ) as conn,
        conn.cursor() as cur,
    ):
        cur.executemany(UPSERT_AIRPORT, airports)
        cur.executemany(UPSERT_RUNWAY, runways)
    return len(airports), len(runways)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--from-dir", type=Path, help="read airports.csv and runways.csv here")
    args = parser.parse_args(argv)
    n_airports, n_runways = load(args.from_dir)
    print(f"upserted {n_airports} airports and {n_runways} runways", file=sys.stderr)


if __name__ == "__main__":
    main()
