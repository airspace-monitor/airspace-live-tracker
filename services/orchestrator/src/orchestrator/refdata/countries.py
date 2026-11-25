"""Natural Earth admin-0 countries, 1:50m (public domain), and the H3 r4 cell → country lookup.

The country code is `ISO_A2_EH`, which fills the `-99` that `ISO_A2` has for France, Norway and
Kosovo. Features still without a code (Somaliland, Northern Cyprus, Siachen Glacier) are skipped;
cells there have no country. Features that share a code (Australia and its external territories)
become one MultiPolygon named after the feature whose own `ISO_A2` is that code. The name is
`ADMIN` (e.g. "Bosnia and Herzegovina", not "Bosnia and Herz.").
"""

import json
import re
from collections.abc import Iterator
from typing import Any

import h3

URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/"
    "ne_50m_admin_0_countries.geojson"
)
ISO_A2 = re.compile(r"^[A-Z]{2}$")
H3_RESOLUTION = 4


def _polygons(geometry: dict[str, Any]) -> list[Any]:
    if geometry["type"] == "Polygon":
        return [geometry["coordinates"]]
    if geometry["type"] == "MultiPolygon":
        return list(geometry["coordinates"])
    raise ValueError(f"unexpected geometry type {geometry['type']}")


def parse_countries(collection: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per ISO code: `iso_a2`, `name`, and `geojson` (a MultiPolygon as text)."""
    merged: dict[str, dict[str, Any]] = {}
    for feature in collection["features"]:
        props = feature["properties"]
        iso = (props.get("ISO_A2_EH") or "").strip().upper()
        if not ISO_A2.match(iso):
            continue
        name = (props.get("ADMIN") or props.get("NAME") or "").strip()
        country = merged.setdefault(iso, {"iso_a2": iso, "name": name, "polygons": []})
        if props.get("ISO_A2") == iso:
            country["name"] = name
        country["polygons"].extend(_polygons(feature["geometry"]))
    return [
        {
            "iso_a2": c["iso_a2"],
            "name": c["name"],
            "geojson": json.dumps({"type": "MultiPolygon", "coordinates": c["polygons"]}),
        }
        for c in merged.values()
    ]


def r4_cell_centres() -> Iterator[tuple[int, float, float]]:
    """Every H3 resolution-4 cell on Earth (288,122) as `(cell, lon, lat)` of its centre."""
    for base in h3.get_res0_cells():
        for cell in h3.cell_to_children(base, H3_RESOLUTION):
            lat, lon = h3.cell_to_latlng(cell)
            yield h3.str_to_int(cell), lon, lat
