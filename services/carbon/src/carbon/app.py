"""carbon-signal HTTP API (docs/05-api-contract.md#carbon-signal-cluster-internal).

Plays the grid operator: the rest of the system reads intensity and a forecast from here and never
computes it itself. A demo override pins the value until it expires; it lives in memory, so a
restart ends it (one replica).
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from airspace_common.log import configure_logging
from airspace_common.settings import CarbonSignalSettings
from airspace_common.timefmt import iso_z
from carbon.curve import intensity, simulated_time

PREFIX = "/v1"
MAX_FORECAST_HOURS = 48
DEFAULT_OVERRIDE = timedelta(hours=1)
MAX_OVERRIDE = timedelta(hours=24)

log = structlog.get_logger()
Clock = Callable[[], datetime]


@dataclass(frozen=True)
class Override:
    intensity_g_kwh: float
    until: datetime


class OverrideRequest(BaseModel):
    intensity_g_kwh: float = Field(gt=0, le=1000)
    until: datetime | None = None


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def _parse_time(raw: str) -> datetime | None:
    try:
        t = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo is not None else None


def build_app(settings: CarbonSignalSettings, clock: Clock | None = None) -> FastAPI:
    now: Clock = clock or (lambda: datetime.now(UTC))
    lock = threading.Lock()
    state: dict[str, Override | None] = {"override": None}
    app = FastAPI(title="airspace carbon-signal", docs_url=None, redoc_url=None)

    def active_override(at: datetime) -> Override | None:
        with lock:
            ov = state["override"]
        return ov if ov is not None and at < ov.until else None

    def reading(at: datetime) -> dict[str, object]:
        sim = simulated_time(at, settings.signal_epoch, settings.signal_time_scale)
        ov = active_override(at)
        value = ov.intensity_g_kwh if ov else intensity(sim, settings.signal_seed)
        return {
            "at": iso_z(at),
            "simulated_at": iso_z(sim),
            "intensity_g_kwh": value,
            "source": "override" if ov else "curve",
        }

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get(f"{PREFIX}/intensity")
    def get_intensity(at: str | None = None) -> JSONResponse:
        t = now()
        if at is not None:
            parsed = _parse_time(at)
            if parsed is None:
                return _error(422, "invalid_time", "at must be ISO 8601 with a UTC offset")
            t = parsed
        return JSONResponse(reading(t))

    @app.get(f"{PREFIX}/forecast")
    def get_forecast(hours: int = 24) -> JSONResponse:
        if not 1 <= hours <= MAX_FORECAST_HOURS:
            return _error(422, "invalid_hours", f"hours must be 1 to {MAX_FORECAST_HOURS}")
        start = now().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        points = [reading(start + timedelta(hours=h)) for h in range(hours)]
        return JSONResponse({"generated_at": iso_z(now()), "points": points})

    @app.put(f"{PREFIX}/override")
    def put_override(body: OverrideRequest) -> JSONResponse:
        t = now()
        until = body.until or t + DEFAULT_OVERRIDE
        if until.tzinfo is None or not t < until <= t + MAX_OVERRIDE:
            return _error(422, "invalid_until", "until must be in the next 24 h, with a UTC offset")
        ov = Override(body.intensity_g_kwh, until.astimezone(UTC))
        with lock:
            state["override"] = ov
        log.info("override_set", intensity_g_kwh=ov.intensity_g_kwh, until=iso_z(ov.until))
        return JSONResponse({"intensity_g_kwh": ov.intensity_g_kwh, "until": iso_z(ov.until)})

    @app.delete(f"{PREFIX}/override", status_code=204)
    def delete_override() -> Response:
        with lock:
            state["override"] = None
        log.info("override_cleared")
        return Response(status_code=204)

    return app


def create_app() -> FastAPI:
    """Entry point for uvicorn."""
    configure_logging("carbon-signal")
    return build_app(CarbonSignalSettings())
