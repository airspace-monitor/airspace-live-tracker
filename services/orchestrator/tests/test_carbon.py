import json
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from orchestrator.carbon import Reading, fetch_reading, window_for_tick

TICK = datetime(2026, 11, 24, 10, 20, tzinfo=UTC)


class Signal(BaseHTTPRequestHandler):
    source = "override"
    seen: list[str] = []

    def do_GET(self) -> None:  # noqa: N802 (http.server's naming)
        url = urlparse(self.path)
        Signal.seen.append(parse_qs(url.query)["at"][0])
        body = json.dumps({"intensity_g_kwh": 412.5, "source": Signal.source}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def signal_url() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Signal)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_the_window_is_the_five_minutes_ending_at_the_tick() -> None:
    start, end = window_for_tick(TICK)
    assert (start.isoformat(), end.isoformat()) == (
        "2026-11-24T10:15:00+00:00",
        "2026-11-24T10:20:00+00:00",
    )


def test_the_reading_is_taken_at_the_window_end(signal_url: str) -> None:
    Signal.source = "override"
    Signal.seen.clear()
    assert fetch_reading(signal_url, TICK) == Reading(TICK, 412.5, "override")
    assert Signal.seen == ["2026-11-24T10:20:00+00:00"]


def test_an_unknown_source_is_an_error(signal_url: str) -> None:
    Signal.source = "guess"
    with pytest.raises(ValueError, match="unexpected source"):
        fetch_reading(signal_url, TICK)
