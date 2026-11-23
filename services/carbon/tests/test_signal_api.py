from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from airspace_common.settings import CarbonSignalSettings
from carbon.app import build_app
from carbon.curve import intensity

NOW = datetime(2026, 11, 24, 10, 20, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.t = NOW

    def __call__(self) -> datetime:
        return self.t


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def client(clock: Clock) -> TestClient:
    return TestClient(build_app(CarbonSignalSettings(signal_seed=7), clock))


def test_health(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}


def test_intensity_now_follows_the_curve(client: TestClient) -> None:
    body = client.get("/v1/intensity").json()
    assert body == {
        "at": "2026-11-24T10:20:00.000Z",
        "simulated_at": "2026-11-24T10:20:00.000Z",
        "intensity_g_kwh": intensity(NOW, 7),
        "source": "curve",
    }


def test_intensity_at_a_given_time(client: TestClient) -> None:
    body = client.get("/v1/intensity", params={"at": "2026-11-20T17:30:00Z"}).json()
    assert body["intensity_g_kwh"] == intensity(datetime(2026, 11, 20, 17, 30, tzinfo=UTC), 7)


@pytest.mark.parametrize("raw", ["yesterday", "2026-11-20T17:30:00"])
def test_intensity_rejects_a_time_without_offset(client: TestClient, raw: str) -> None:
    r = client.get("/v1/intensity", params={"at": raw})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_time"


def test_forecast_is_hourly_from_the_next_full_hour(client: TestClient) -> None:
    points = client.get("/v1/forecast", params={"hours": 3}).json()["points"]
    assert [p["at"] for p in points] == [
        "2026-11-24T11:00:00.000Z",
        "2026-11-24T12:00:00.000Z",
        "2026-11-24T13:00:00.000Z",
    ]


@pytest.mark.parametrize("hours", [0, 49])
def test_forecast_hours_are_bounded(client: TestClient, hours: int) -> None:
    assert client.get("/v1/forecast", params={"hours": hours}).status_code == 422


def test_override_pins_the_value_until_it_expires(client: TestClient, clock: Clock) -> None:
    r = client.put("/v1/override", json={"intensity_g_kwh": 420})
    assert r.json() == {"intensity_g_kwh": 420.0, "until": "2026-11-24T11:20:00.000Z"}
    assert client.get("/v1/intensity").json()["source"] == "override"
    assert client.get("/v1/intensity").json()["intensity_g_kwh"] == 420.0
    # The forecast shows the override for the hours it still covers.
    points = client.get("/v1/forecast", params={"hours": 2}).json()["points"]
    assert [p["source"] for p in points] == ["override", "curve"]
    clock.t = NOW + timedelta(hours=1)
    assert client.get("/v1/intensity").json()["source"] == "curve"


def test_override_can_be_cleared(client: TestClient) -> None:
    client.put("/v1/override", json={"intensity_g_kwh": 150, "until": "2026-11-24T18:00:00Z"})
    assert client.delete("/v1/override").status_code == 204
    assert client.get("/v1/intensity").json()["source"] == "curve"


@pytest.mark.parametrize(
    "body",
    [
        {"intensity_g_kwh": 0},
        {"intensity_g_kwh": 1001},
        {"intensity_g_kwh": 300, "until": "2026-11-24T09:00:00Z"},  # in the past
        {"intensity_g_kwh": 300, "until": "2026-11-26T09:00:00Z"},  # more than 24 h
        {"intensity_g_kwh": 300, "until": "2026-11-24T12:00:00"},  # no offset
    ],
)
def test_invalid_overrides_are_rejected(client: TestClient, body: dict[str, object]) -> None:
    assert client.put("/v1/override", json=body).status_code == 422
    assert client.get("/v1/intensity").json()["source"] == "curve"


def test_a_sped_up_clock_moves_through_the_day(clock: Clock) -> None:
    settings = CarbonSignalSettings(signal_time_scale=60, signal_epoch=NOW)
    client = TestClient(build_app(settings, clock))
    clock.t = NOW + timedelta(minutes=6)
    assert client.get("/v1/intensity").json()["simulated_at"] == "2026-11-24T16:20:00.000Z"
