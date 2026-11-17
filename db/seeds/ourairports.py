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
import csv
import io
import sys
import urllib.request
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any, TextIO

BASE_URL = "https://davidmegginson.github.io/ourairports-data/"
TARGET_AIRPORTS = {"LOWW", "LZIB", "LHBP"}
FT_TO_M = 0.3048


def _text(value: str) -> str | None:
    value = value.strip()
    return value or None


def _float(value: str) -> float | None:
    value = value.strip()
    return float(value) if value else None


def parse_airports(f: TextIO) -> Iterator[dict[str, Any]]:
    for row in csv.DictReader(f):
        icao = _text(row["icao_code"])
        elevation_ft = _float(row["elevation_ft"])
        if icao is None or elevation_ft is None:
            continue
        yield {
            "icao": icao,
            "iata": _text(row["iata_code"]),
            "name": row["name"].strip(),
            "type": row["type"].strip(),
            "lat": float(row["latitude_deg"]),
            "lon": float(row["longitude_deg"]),
            "elevation_m": elevation_ft * FT_TO_M,
            "country": _text(row["iso_country"]),
            "is_target": icao in TARGET_AIRPORTS,
            "_id": row["id"],
        }


def parse_runways(
    f: TextIO, airport_icaos: Iterable[str], ids_to_icao: dict[str, str] | None = None
) -> Iterator[dict[str, Any]]:
    """Runways of the given airports. Rows are matched on `airport_ident` when it is a loaded
    ICAO code, or through `ids_to_icao` (OurAirports id → ICAO) when the ident differs."""
    icaos = set(airport_icaos)
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for row in csv.DictReader(f):
        icao = (ids_to_icao or {}).get(row["airport_ref"]) or row["airport_ident"].strip()
        le_ident = _text(row["le_ident"])
        if icao not in icaos or le_ident is None or row["closed"].strip() == "1":
            continue
        length_ft = _float(row["length_ft"])
        runway = {
            "airport_icao": icao,
            "le_ident": le_ident,
            "he_ident": _text(row["he_ident"]),
            "le_heading_deg": _float(row["le_heading_degT"]),
            "he_heading_deg": _float(row["he_heading_degT"]),
            "length_m": length_ft * FT_TO_M if length_ft is not None else None,
        }
        key = (icao, le_ident)
        kept = best.get(key)
        if kept is None or (runway["length_m"] or 0) > (kept["length_m"] or 0):
            best[key] = runway
    yield from best.values()


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
