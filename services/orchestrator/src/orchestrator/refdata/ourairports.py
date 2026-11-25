"""OurAirports airports and runways (docs/02-data-sources.md#reference-data), public domain.

Rows that are skipped (Q4, decided 2026-11-17):
- airports without an ICAO code, or without an elevation (`elevation_m` is required; a guessed 0
  would give wrong heights above the airport);
- closed runways, runways without an `le_ident`, and runways of airports that were skipped;
- a repeated `(airport, le_ident)`: the longest runway is kept.
"""

import csv
from collections.abc import Iterable, Iterator
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
