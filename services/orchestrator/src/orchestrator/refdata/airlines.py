"""OpenFlights `airlines.dat` (ODbL 1.0, attribution in the README).

Columns: id, name, alias, IATA, ICAO, callsign, country, active; `\\N` is NULL. Only active
airlines with a three-letter ICAO code are kept (docs/03-data-model.md). OpenFlights lists some
ICAO codes more than once; the first active entry wins.
"""

import csv
import re
from collections.abc import Iterator
from typing import Any, TextIO

URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airlines.dat"
ICAO = re.compile(r"^[A-Z]{3}$")


def _text(value: str) -> str | None:
    value = value.strip()
    return None if value in ("", "\\N", "-", "N/A") else value


def parse_airlines(f: TextIO) -> Iterator[dict[str, Any]]:
    seen: set[str] = set()
    for row in csv.reader(f):
        if len(row) < 8 or row[7].strip() != "Y":
            continue
        icao, name = (_text(row[4]) or "").upper(), _text(row[1])
        if not ICAO.match(icao) or name is None or icao in seen:
            continue
        seen.add(icao)
        yield {"icao": icao, "name": name, "country": _text(row[6])}
