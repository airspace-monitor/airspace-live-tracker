from pathlib import Path

from ourairports import parse_airports, parse_runways

FIXTURE = Path(__file__).parents[1] / "tests" / "ourairports"


def airports() -> dict[str, dict]:
    with (FIXTURE / "airports.csv").open(encoding="utf-8") as f:
        return {a["icao"]: a for a in parse_airports(f)}


def runways(icaos: set[str]) -> list[dict]:
    with (FIXTURE / "runways.csv").open(encoding="utf-8") as f:
        return list(parse_runways(f, icaos))


def test_only_airports_with_an_icao_code_and_an_elevation_are_loaded() -> None:
    assert sorted(airports()) == ["LHBP", "LOAN", "LOWW", "LZIB"]


def test_target_airports_are_flagged_and_converted_to_si_units() -> None:
    a = airports()
    assert [icao for icao, row in sorted(a.items()) if row["is_target"]] == ["LHBP", "LOWW", "LZIB"]
    loww = a["LOWW"]
    assert loww["elevation_m"] == 600 * 0.3048
    assert (loww["lat"], loww["lon"]) == (48.110298, 16.5697)
    assert (loww["iata"], loww["country"], loww["type"]) == ("VIE", "AT", "large_airport")


def test_empty_codes_become_null() -> None:
    assert airports()["LOAN"]["iata"] is None


def test_runways_skip_missing_identifiers_closed_rows_and_unknown_airports() -> None:
    rows = runways(set(airports()))
    assert sorted((r["airport_icao"], r["le_ident"]) for r in rows) == [
        ("LOAN", "05"),
        ("LOWW", "11"),
        ("LOWW", "16"),
    ]


def test_a_duplicate_runway_identifier_keeps_the_longest() -> None:
    [loan05] = [r for r in runways(set(airports())) if r["airport_icao"] == "LOAN"]
    assert loan05["length_m"] == 4000 * 0.3048


def test_runway_headings_and_ends_are_kept() -> None:
    [r11] = [r for r in runways(set(airports())) if r["le_ident"] == "11"]
    assert (r11["he_ident"], r11["le_heading_deg"], r11["he_heading_deg"]) == ("29", 116.0, 296.0)
