import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from orchestrator.metar import (
    ceiling_m,
    fetch,
    in_window,
    lookback_hours,
    parse,
    visibility_from_raw,
    window_for_tick,
)

# Two records as aviationweather.gov returned them on 2026-11-25 (trimmed to the fields we read).
LOWW: dict[str, Any] = {
    "icaoId": "LOWW",
    "obsTime": 1795609200,
    "temp": 2,
    "dewp": -4,
    "wdir": 100,
    "wspd": 7,
    "visib": "6+",
    "altim": 1018,
    "rawOb": "METAR LOWW 251220Z 10007KT 070V140 9999 FEW028 BKN030 02/M04 Q1018 NOSIG",
    "clouds": [{"cover": "FEW", "base": 2800}, {"cover": "BKN", "base": 3000}],
    "fltCat": "MVFR",
}
LHBP: dict[str, Any] = {
    "icaoId": "LHBP",
    "obsTime": 1795599000,
    "temp": 1,
    "dewp": -2,
    "wdir": "VRB",
    "wspd": 1,
    "visib": "6+",
    "altim": 1024,
    "rawOb": "METAR LHBP 250930Z VRB01KT CAVOK 01/M02 Q1024 NOSIG",
    "clouds": [],
    "fltCat": "VFR",
}


def test_a_report_is_stored_in_si_units() -> None:
    m = parse(LOWW)
    assert m is not None
    assert m.station == "LOWW"
    assert m.observed_at == datetime(2026, 11, 25, 12, 20, tzinfo=UTC)
    assert m.wind_dir_deg == 100
    assert m.wind_speed_ms == pytest.approx(3.6, abs=0.01)
    assert m.gust_ms is None
    assert m.visibility_m == 10_000
    assert m.ceiling_m == 914  # BKN030: 3000 ft
    assert (m.temp_c, m.dewpoint_c, m.qnh_hpa) == (2.0, -4.0, 1018.0)
    assert m.flight_category == "MVFR"
    assert m.raw_text == LOWW["rawOb"]


def test_variable_wind_has_no_direction_and_cavok_is_ten_km() -> None:
    m = parse(LHBP)
    assert m is not None
    assert m.wind_dir_deg is None
    assert m.visibility_m == 10_000
    assert m.ceiling_m is None


def test_gusts_are_converted() -> None:
    m = parse({**LOWW, "wgst": 25})
    assert m is not None and m.gust_ms == pytest.approx(12.86, abs=0.01)


@pytest.mark.parametrize(
    ("raw", "metres"),
    [
        ("METAR LZIB 251200Z 08011KT 9999 FEW021 02/M03 Q1020", 10_000),
        ("METAR LZIB 251200Z 08011G21KT 0800 R22/1000N FG", 800),
        ("METAR LOWW 251200Z 10007KT 070V140 4500 BR", 4500),
        ("METAR LOWW 251200Z 10007KT 4500NDV BR", 4500),
        ("METAR KJFK 251151Z 31012KT 10SM FEW250", None),
        ("METAR LOWW 251200Z", None),
    ],
)
def test_visibility_comes_from_the_raw_report(raw: str, metres: int | None) -> None:
    assert visibility_from_raw(raw) == metres


def test_visibility_falls_back_to_statute_miles() -> None:
    m = parse({**LOWW, "rawOb": "METAR KJFK 251151Z 31012KT 10SM FEW250", "visib": "6+"})
    assert m is not None and m.visibility_m == 9656


def test_the_ceiling_is_the_lowest_broken_overcast_or_vertical_visibility_layer() -> None:
    assert ceiling_m([{"cover": "SCT", "base": 1000}, {"cover": "OVC", "base": 5000}]) == 1524
    assert ceiling_m([{"cover": "VV", "base": 200}, {"cover": "BKN", "base": 900}]) == 61
    assert ceiling_m([{"cover": "OVX", "base": 100}]) == 30
    assert ceiling_m([{"cover": "FEW", "base": 2000}]) is None
    assert ceiling_m([{"cover": "OVC", "base": None}]) is None
    assert ceiling_m(None) is None


def test_unknown_flight_categories_are_dropped() -> None:
    m = parse({**LOWW, "fltCat": "UNK"})
    assert m is not None and m.flight_category is None


@pytest.mark.parametrize("missing", ["icaoId", "obsTime", "rawOb"])
def test_records_without_station_time_or_text_are_skipped(missing: str) -> None:
    assert parse({k: v for k, v in LOWW.items() if k != missing}) is None


def test_only_target_stations_inside_the_window_are_kept() -> None:
    start = datetime(2026, 11, 25, 10, 0, tzinfo=UTC)
    end = datetime(2026, 11, 25, 12, 20, tzinfo=UTC)
    records = [
        LOWW,  # 12:20, at the window end: excluded
        {**LOWW, "obsTime": LOWW["obsTime"] - 1800},  # 11:50
        {**LOWW, "icaoId": "EDDM", "obsTime": LOWW["obsTime"] - 1800},  # not a target
        LHBP,  # 09:30, before the window
        {**LHBP, "obsTime": LHBP["obsTime"] + 1800},  # 10:00, at the window start
    ]
    kept = in_window(records, ["LHBP", "LOWW", "LZIB"], start, end)
    assert sorted((m.station, m.observed_at.strftime("%H:%M")) for m in kept) == [
        ("LHBP", "10:00"),
        ("LOWW", "11:50"),
    ]


def test_a_repeated_report_is_kept_once() -> None:
    start = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)
    end = start + timedelta(hours=1)
    assert len(in_window([LOWW, LOWW], ["LOWW"], start, end)) == 1


def test_the_window_is_the_three_hours_ending_at_the_tick() -> None:
    tick = datetime(2026, 11, 25, 12, 35, tzinfo=UTC)
    start, end = window_for_tick(tick)
    assert (start, end) == (datetime(2026, 11, 25, 9, 35, tzinfo=UTC), tick)


def test_lookback_covers_the_window_start() -> None:
    now = datetime(2026, 11, 25, 12, 36, tzinfo=UTC)
    assert lookback_hours(now - timedelta(hours=3, minutes=1), now) == 4
    assert lookback_hours(now - timedelta(hours=3), now) == 3
    assert lookback_hours(now, now) == 1
    with pytest.raises(ValueError, match="metar_backfill"):
        lookback_hours(now - timedelta(days=16), now)


class Api(BaseHTTPRequestHandler):
    status = 200
    body = b"[]"
    seen: list[dict[str, list[str]]] = []
    agents: list[str] = []

    def do_GET(self) -> None:  # noqa: N802 (http.server's naming)
        Api.seen.append(parse_qs(urlparse(self.path).query))
        Api.agents.append(self.headers.get("User-Agent", ""))
        self.send_response(Api.status)
        self.end_headers()
        if Api.status == 200:
            self.wfile.write(Api.body)

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def api_url() -> Iterator[str]:
    Api.seen.clear()
    Api.agents.clear()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Api)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/api/data/metar"
    server.shutdown()


def test_fetch_asks_for_the_stations_and_hours(api_url: str) -> None:
    Api.status, Api.body = 200, b'[{"icaoId": "LOWW"}]'
    assert fetch(api_url, ["LHBP", "LOWW"], 3) == [{"icaoId": "LOWW"}]
    assert Api.seen == [{"ids": ["LHBP,LOWW"], "format": ["json"], "hours": ["3"]}]
    assert Api.agents == ["airspace-monitor metar_fetch"]


def test_no_reports_is_an_empty_list(api_url: str) -> None:
    Api.status = 204
    assert fetch(api_url, ["LOWW"], 3) == []


def test_an_unexpected_body_is_an_error(api_url: str) -> None:
    Api.status, Api.body = 200, b'{"error": "bad"}'
    with pytest.raises(ValueError, match="JSON list"):
        fetch(api_url, ["LOWW"], 3)
