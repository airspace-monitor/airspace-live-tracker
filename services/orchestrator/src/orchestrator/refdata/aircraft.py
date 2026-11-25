"""The OpenSky aircraft database (non-commercial use, attribution in the UI and README).

OpenSky publishes monthly snapshots `metadata/aircraft-database-complete-YYYY-MM.csv` in its
public `data-samples` bucket; the newest one is loaded. The CSV quotes with single quotes and may
list an `icao24` more than once: the row with the latest `timestamp` wins.
"""

import csv
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from typing import Any, TextIO

BUCKET_URL = "https://s3.opensky-network.org/data-samples"
LISTING_URL = f"{BUCKET_URL}?list-type=2&prefix=metadata/aircraft-database-complete-"
SNAPSHOT = re.compile(r"^metadata/aircraft-database-complete-(\d{4}-\d{2})\.csv$")
ICAO24 = re.compile(r"^[0-9a-f]{6}$")

# Column → ref.aircraft column.
COLUMNS = {
    "registration": "registration",
    "typecode": "typecode",
    "manufacturerName": "manufacturer",
    "model": "model",
    "operator": "operator",
    "operatorIcao": "operator_icao",
}


def latest_snapshot(listing_xml: bytes) -> str:
    """The key of the newest monthly snapshot in an S3 ListObjectsV2 response."""
    root = ET.fromstring(listing_xml)
    keys = [el.text or "" for el in root.iter() if el.tag.endswith("Key")]
    snapshots = sorted(k for k in keys if SNAPSHOT.match(k))
    if not snapshots:
        raise ValueError("no aircraft-database-complete-YYYY-MM.csv in the OpenSky bucket")
    return snapshots[-1]


def _text(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def parse_aircraft(f: TextIO) -> Iterator[dict[str, Any]]:
    latest: dict[str, tuple[str, dict[str, Any]]] = {}
    for row in csv.DictReader(f, quotechar="'"):
        icao24 = (row.get("icao24") or "").strip().lower()
        if not ICAO24.match(icao24):
            continue
        record: dict[str, Any] = {"icao24": icao24}
        record.update({ours: _text(row.get(theirs)) for theirs, ours in COLUMNS.items()})
        if record["operator_icao"]:
            record["operator_icao"] = record["operator_icao"].upper()
        if all(record[c] is None for c in COLUMNS.values()):
            continue
        stamp = row.get("timestamp") or ""
        kept = latest.get(icao24)
        if kept is None or stamp >= kept[0]:
            latest[icao24] = (stamp, record)
    for _, record in latest.values():
        yield record
