"""`metar_fetch` (docs/04-pipelines.md#metar_fetch).

Every 30 minutes, fetches the target airports' METARs of the last 3 hours from aviationweather.gov
(docs/02-data-sources.md#weather-metar) and upserts them into `core.metar` in SI units. Reports
outside the window are dropped, so a run only ever writes its own window. A replayed window
writes nothing new; a corrected report (same station and time, different text) replaces the old
one.
"""

import json
import math
import re
import urllib.parse
import urllib.request
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
from dagster import (
    Config,
    DefaultScheduleStatus,
    OpExecutionContext,
    RunRequest,
    ScheduleEvaluationContext,
    job,
    op,
    schedule,
)

from airspace_common.settings import JobsSettings
from orchestrator.job_runs import recorded_run

WINDOW = timedelta(hours=3)
# aviationweather.gov serves the last 15 days; older windows are `metar_backfill`'s.
MAX_LOOKBACK = timedelta(days=15)
TIMEOUT_S = 30
USER_AGENT = "airspace-monitor metar_fetch"

KT_TO_MS = 0.514444
FT_TO_M = 0.3048
SM_TO_M = 1609.344
CEILING_COVERS = {"BKN", "OVC", "OVX", "VV"}
FLIGHT_CATEGORIES = {"VFR", "MVFR", "IFR", "LIFR"}

WIND_GROUP = re.compile(r"^(\d{3}|VRB)\d{2,3}(G\d{2,3})?(KT|MPS)$")
VARIABLE_WIND = re.compile(r"^\d{3}V\d{3}$")
VISIBILITY_M = re.compile(r"^(\d{4})(NDV)?$")

UPSERT_SQL = """
INSERT INTO core.metar (station, observed_at, raw_text, wind_dir_deg, wind_speed_ms, gust_ms,
                        visibility_m, ceiling_m, temp_c, dewpoint_c, qnh_hpa, flight_category)
VALUES (%(station)s, %(observed_at)s, %(raw_text)s, %(wind_dir_deg)s, %(wind_speed_ms)s,
        %(gust_ms)s, %(visibility_m)s, %(ceiling_m)s, %(temp_c)s, %(dewpoint_c)s, %(qnh_hpa)s,
        %(flight_category)s)
ON CONFLICT (station, observed_at) DO UPDATE SET
  raw_text = EXCLUDED.raw_text, wind_dir_deg = EXCLUDED.wind_dir_deg,
  wind_speed_ms = EXCLUDED.wind_speed_ms, gust_ms = EXCLUDED.gust_ms,
  visibility_m = EXCLUDED.visibility_m, ceiling_m = EXCLUDED.ceiling_m,
  temp_c = EXCLUDED.temp_c, dewpoint_c = EXCLUDED.dewpoint_c, qnh_hpa = EXCLUDED.qnh_hpa,
  flight_category = EXCLUDED.flight_category
WHERE core.metar.raw_text IS DISTINCT FROM EXCLUDED.raw_text
"""


@dataclass(frozen=True)
class Metar:
    station: str
    observed_at: datetime
    raw_text: str
    wind_dir_deg: int | None
    wind_speed_ms: float | None
    gust_ms: float | None
    visibility_m: int | None
    ceiling_m: int | None
    temp_c: float | None
    dewpoint_c: float | None
    qnh_hpa: float | None
    flight_category: str | None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).rstrip("+"))
    except ValueError:
        return None


def _knots(value: Any) -> float | None:
    kt = _number(value)
    return None if kt is None else round(kt * KT_TO_MS, 2)


def visibility_from_raw(raw: str) -> int | None:
    """Metres from the raw report's visibility group (the token after the wind), or None when the
    report gives none in metres (e.g. statute miles)."""
    tokens = raw.split()
    for i, token in enumerate(tokens):
        if WIND_GROUP.match(token):
            rest = tokens[i + 1 :]
            if rest and VARIABLE_WIND.match(rest[0]):
                rest = rest[1:]
            if not rest:
                return None
            if rest[0] == "CAVOK":
                return 10_000
            m = VISIBILITY_M.match(rest[0])
            if m:
                metres = int(m.group(1))
                return 10_000 if metres == 9999 else metres
            return None
    return None


def visibility_m(record: dict[str, Any]) -> int | None:
    from_raw = visibility_from_raw(record.get("rawOb") or "")
    if from_raw is not None:
        return from_raw
    sm = _number(record.get("visib"))
    return None if sm is None else round(sm * SM_TO_M)


def ceiling_m(clouds: Iterable[dict[str, Any]] | None) -> int | None:
    """The lowest broken, overcast or vertical-visibility base; None when there is none."""
    bases = [
        c["base"]
        for c in clouds or []
        if c.get("cover") in CEILING_COVERS and isinstance(c.get("base"), (int, float))
    ]
    return round(min(bases) * FT_TO_M) if bases else None


def parse(record: dict[str, Any]) -> Metar | None:
    """One aviationweather.gov JSON record in SI units, or None if it lacks a station, time or
    raw text."""
    station, obs, raw = record.get("icaoId"), record.get("obsTime"), record.get("rawOb")
    if not station or not isinstance(obs, (int, float)) or not raw:
        return None
    wdir = record.get("wdir")
    category = record.get("fltCat")
    return Metar(
        station=str(station).upper(),
        observed_at=datetime.fromtimestamp(obs, UTC),
        raw_text=str(raw),
        wind_dir_deg=int(wdir) if isinstance(wdir, (int, float)) else None,
        wind_speed_ms=_knots(record.get("wspd")),
        gust_ms=_knots(record.get("wgst")),
        visibility_m=visibility_m(record),
        ceiling_m=ceiling_m(record.get("clouds")),
        temp_c=_number(record.get("temp")),
        dewpoint_c=_number(record.get("dewp")),
        qnh_hpa=_number(record.get("altim")),
        flight_category=category if category in FLIGHT_CATEGORIES else None,
    )


def lookback_hours(start: datetime, now: datetime) -> int:
    """The API's `hours` (counted back from now) that covers a window starting at `start`."""
    if now - start > MAX_LOOKBACK:
        raise ValueError(
            f"window starts {start.isoformat()}, more than 15 days ago; use metar_backfill"
        )
    return max(1, math.ceil((now - start) / timedelta(hours=1)))


def fetch(base_url: str, stations: Sequence[str], hours: int) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"ids": ",".join(stations), "format": "json", "hours": hours})
    req = urllib.request.Request(f"{base_url}?{query}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        body = r.read()
    # 204 (no reports) comes with an empty body.
    if not body.strip():
        return []
    data = json.loads(body)
    if not isinstance(data, list):
        raise ValueError(f"expected a JSON list, got {type(data).__name__}")
    return data


def in_window(
    records: Iterable[dict[str, Any]], stations: Sequence[str], start: datetime, end: datetime
) -> list[Metar]:
    wanted = set(stations)
    out = {}
    for record in records:
        m = parse(record)
        if m and m.station in wanted and start <= m.observed_at < end:
            out[(m.station, m.observed_at)] = m
    return list(out.values())


def target_stations(conn: psycopg.Connection) -> list[str]:
    rows = conn.execute("SELECT icao FROM ref.airports WHERE is_target ORDER BY icao").fetchall()
    return [r[0] for r in rows]


def store(conn: psycopg.Connection, metars: Iterable[Metar]) -> int:
    """Upserts; returns the number of reports that were new or changed."""
    written = 0
    with conn.cursor() as cur:
        for m in metars:
            cur.execute(UPSERT_SQL, m.__dict__)
            written += cur.rowcount
    return written


class MetarWindow(Config):
    """The explicit `[window_start, window_end)` (ISO 8601 with a UTC offset)."""

    window_start: str
    window_end: str


@op
def metar_fetch_op(context: OpExecutionContext, config: MetarWindow) -> None:
    start = datetime.fromisoformat(config.window_start)
    end = datetime.fromisoformat(config.window_end)
    settings = JobsSettings()
    with recorded_run(settings, "metar_fetch", start, end) as run:
        stations = target_stations(run.conn)
        if not stations:
            raise ValueError("ref.airports has no target airports (is_target)")
        records = fetch(settings.metar_url, stations, lookback_hours(start, datetime.now(UTC)))
        metars = in_window(records, stations, start, end)
        run.rows_out = store(run.conn, metars)
    context.log.info(f"{len(metars)} reports for {','.join(stations)}, {run.rows_out} new")


@job(description="Upsert the target airports' METARs of the last 3 hours into core.metar.")
def metar_fetch() -> None:
    metar_fetch_op()


def window_for_tick(tick: datetime) -> tuple[datetime, datetime]:
    return tick - WINDOW, tick


@schedule(
    job=metar_fetch,
    cron_schedule="5,35 * * * *",
    execution_timezone="UTC",
    default_status=DefaultScheduleStatus.RUNNING,
)
def metar_fetch_schedule(context: ScheduleEvaluationContext) -> RunRequest:
    tick = context.scheduled_execution_time or datetime.now(UTC)
    start, end = window_for_tick(tick.astimezone(UTC))
    window = {"window_start": start.isoformat(), "window_end": end.isoformat()}
    return RunRequest(
        run_key=window["window_end"],
        run_config={"ops": {"metar_fetch_op": {"config": window}}},
    )
