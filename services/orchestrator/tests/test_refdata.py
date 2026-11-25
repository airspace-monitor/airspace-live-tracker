import json
from pathlib import Path

import h3
import pytest

from orchestrator.ref_refresh import Sources, check_shrink, load_sources
from orchestrator.refdata.aircraft import latest_snapshot, parse_aircraft
from orchestrator.refdata.airlines import parse_airlines
from orchestrator.refdata.countries import parse_countries, r4_cell_centres

FIXTURES = Path(__file__).parents[3] / "db" / "tests" / "refdata"


def aircraft() -> dict[str, dict]:
    with (FIXTURES / "aircraft.csv").open(encoding="utf-8", newline="") as f:
        return {a["icao24"]: a for a in parse_aircraft(f)}


def test_aircraft_keep_the_latest_row_per_icao24_in_lower_case() -> None:
    a = aircraft()
    assert sorted(a) == ["000000", "3b7d41", "440017", "4b1805"]
    assert a["440017"] == {
        "icao24": "440017",
        "registration": "OE-LBM",
        "typecode": "A320",
        "manufacturer": "Airbus",
        "model": "A320 214",
        "operator": "Austrian Airlines",
        "operator_icao": "AUA",
    }


def test_single_quoted_fields_keep_their_apostrophes() -> None:
    assert aircraft()["3b7d41"]["operator"] == "Ecole Nationale De L'aviation Civile"


def test_empty_aircraft_fields_are_null() -> None:
    a = aircraft()["4b1805"]
    assert a["manufacturer"] == "C Series Aircraft Limited Partnership"
    assert aircraft()["000000"]["registration"] is None


def test_the_newest_monthly_snapshot_is_chosen() -> None:
    listing = b"""<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
  <Contents><Key>metadata/aircraft-database-complete-2025-02.csv</Key></Contents>
  <Contents><Key>metadata/aircraft-database-complete-2025-08.csv</Key></Contents>
  <Contents><Key>metadata/aircraft-database-complete-2024-10.csv</Key></Contents>
  <Contents><Key>metadata/aircraftDatabase.csv</Key></Contents>
</ListBucketResult>"""
    assert latest_snapshot(listing) == "metadata/aircraft-database-complete-2025-08.csv"


def test_a_listing_without_snapshots_is_an_error() -> None:
    with pytest.raises(ValueError, match="aircraft-database-complete"):
        latest_snapshot(b"<ListBucketResult></ListBucketResult>")


def test_airlines_keep_active_three_letter_icao_codes_once() -> None:
    with (FIXTURES / "airlines.dat").open(encoding="utf-8", newline="") as f:
        rows = list(parse_airlines(f))
    assert rows == [
        {"icao": "AUA", "name": "Austrian Airlines", "country": "Austria"},
        {"icao": "DLH", "name": "Lufthansa", "country": "Germany"},
        {"icao": "SWR", "name": "Swiss International Air Lines", "country": "Switzerland"},
    ]


def countries() -> dict[str, dict]:
    collection = json.loads((FIXTURES / "countries.geojson").read_text(encoding="utf-8"))
    return {c["iso_a2"]: c for c in parse_countries(collection)}


def test_countries_use_the_filled_iso_code_and_skip_codeless_ones() -> None:
    assert sorted(countries()) == ["AT", "FR", "SK"]
    assert countries()["FR"]["name"] == "France"


def test_countries_are_multipolygons() -> None:
    for c in countries().values():
        assert json.loads(c["geojson"])["type"] == "MultiPolygon"
    assert len(json.loads(countries()["FR"]["geojson"])["coordinates"]) == 2


def test_features_sharing_a_code_merge_under_the_main_name() -> None:
    def feature(iso: str, eh: str, name: str, x: float) -> dict:
        ring = [[x, 0], [x + 1, 0], [x + 1, 1], [x, 1], [x, 0]]
        props = {"ISO_A2": iso, "ISO_A2_EH": eh, "ADMIN": name}
        return {"properties": props, "geometry": {"type": "Polygon", "coordinates": [ring]}}

    [au] = parse_countries(
        {
            "features": [
                feature("-99", "AU", "Indian Ocean Territories", 0),
                feature("AU", "AU", "Australia", 2),
                feature("-99", "AU", "Ashmore and Cartier Islands", 4),
            ]
        }
    )
    assert au["name"] == "Australia"
    assert len(json.loads(au["geojson"])["coordinates"]) == 3


def test_every_r4_cell_is_listed_once_with_its_centre() -> None:
    cells = list(r4_cell_centres())
    assert len(cells) == len({c for c, _, _ in cells}) == 288_122
    vienna = h3.str_to_int(h3.latlng_to_cell(48.11, 16.57, 4))
    [(_, lon, lat)] = [c for c in cells if c[0] == vienna]
    assert abs(lat - 48.11) < 0.5 and abs(lon - 16.57) < 0.5


def test_all_fixture_sources_load_from_a_directory() -> None:
    rows, snapshot = load_sources(Sources(str(FIXTURES)))
    assert snapshot == "aircraft.csv"
    assert {k: len(v) for k, v in rows.items()} == {
        "airports": 4,
        "runways": 3,
        "aircraft": 4,
        "airlines": 3,
        "countries": 3,
    }
    assert all("_id" not in a for a in rows["airports"])


def test_a_dataset_that_halves_is_refused() -> None:
    check_shrink("ref.aircraft", 0, 0)
    check_shrink("ref.aircraft", 100, 50)
    with pytest.raises(ValueError, match="refusing to replace"):
        check_shrink("ref.aircraft", 100, 49)
