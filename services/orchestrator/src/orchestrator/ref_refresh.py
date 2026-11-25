"""`ref_refresh` (docs/04-pipelines.md#ref_refresh).

Monthly full reload of `ref.*` except `callsign_routes`: airports and runways (OurAirports),
aircraft (OpenSky aircraft database), airlines (OpenFlights), countries (Natural Earth), then
`ref.h3_r4_country` from the countries. Every dataset is downloaded and parsed first and staged
in temporary tables; then one transaction makes each table equal to its staged copy (rows that
disappeared upstream are deleted, changed rows updated, new rows inserted). A run that fails
anywhere changes nothing, and re-running it changes nothing more.

A dataset that shrinks to under half its current row count aborts the run: that is a broken
download or a format change, not a real change in the world.
"""

import io
import json
import shutil
import tempfile
import urllib.request
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

import psycopg
from dagster import (
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
from orchestrator.refdata import aircraft, airlines, countries, ourairports

USER_AGENT = "airspace-monitor ref_refresh"
TIMEOUT_S = 300
MIN_SHARE = 0.5

AIRPORT_COLS = ("icao", "iata", "name", "type", "lat", "lon", "elevation_m", "country", "is_target")
RUNWAY_COLS = (
    "airport_icao",
    "le_ident",
    "he_ident",
    "le_heading_deg",
    "he_heading_deg",
    "length_m",
)
AIRCRAFT_COLS = (
    "icao24",
    "registration",
    "typecode",
    "manufacturer",
    "model",
    "operator",
    "operator_icao",
)
AIRLINE_COLS = ("icao", "name", "country")
COUNTRY_COLS = ("iso_a2", "name", "geojson")


class Sources:
    """Where the raw files come from: the internet, or a directory with the same file names
    (`REF_SOURCE_DIR`, used by CI)."""

    def __init__(self, source_dir: str | None) -> None:
        self.dir = Path(source_dir) if source_dir else None

    @staticmethod
    def _get(url: str) -> urllib.request.Request:
        return urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    @contextmanager
    def text(self, name: str, url: str) -> Iterator[TextIO]:
        if self.dir is not None:
            with (self.dir / name).open(encoding="utf-8", newline="") as f:
                yield f
            return
        with urllib.request.urlopen(self._get(url), timeout=TIMEOUT_S) as r:
            yield io.StringIO(r.read().decode("utf-8"), newline="")

    @contextmanager
    def aircraft(self) -> Iterator[tuple[str, TextIO]]:
        """The newest monthly snapshot, spooled to a temporary file (~110 MB)."""
        if self.dir is not None:
            with (self.dir / "aircraft.csv").open(encoding="utf-8", newline="") as f:
                yield "aircraft.csv", f
            return
        with urllib.request.urlopen(self._get(aircraft.LISTING_URL), timeout=TIMEOUT_S) as r:
            key = aircraft.latest_snapshot(r.read())
        with tempfile.TemporaryFile() as tmp:
            url = f"{aircraft.BUCKET_URL}/{key}"
            with urllib.request.urlopen(self._get(url), timeout=TIMEOUT_S) as r:
                shutil.copyfileobj(r, tmp)
            tmp.seek(0)
            yield key, io.TextIOWrapper(tmp, encoding="utf-8", newline="")


def load_sources(src: Sources) -> tuple[dict[str, list[dict[str, Any]]], str]:
    with src.text("airports.csv", ourairports.BASE_URL + "airports.csv") as f:
        airports = list(ourairports.parse_airports(f))
    ids_to_icao = {a.pop("_id"): a["icao"] for a in airports}
    missing = ourairports.TARGET_AIRPORTS - set(ids_to_icao.values())
    if missing:
        raise ValueError(f"target airports missing from OurAirports: {sorted(missing)}")
    with src.text("runways.csv", ourairports.BASE_URL + "runways.csv") as f:
        runways = list(ourairports.parse_runways(f, ids_to_icao.values(), ids_to_icao))
    with src.aircraft() as (snapshot, f):
        planes = list(aircraft.parse_aircraft(f))
    with src.text("airlines.dat", airlines.URL) as f:
        carriers = list(airlines.parse_airlines(f))
    with src.text("countries.geojson", countries.URL) as f:
        nations = countries.parse_countries(json.load(f))
    rows = {
        "airports": airports,
        "runways": runways,
        "aircraft": planes,
        "airlines": carriers,
        "countries": nations,
    }
    return rows, snapshot


def _stage(
    cur: psycopg.Cursor[Any],
    name: str,
    ddl: str,
    cols: Sequence[str],
    rows: Iterable[dict[str, Any]],
) -> None:
    cur.execute(f"CREATE TEMP TABLE {name} ON COMMIT DROP AS {ddl}")
    with cur.copy(f"COPY {name} ({', '.join(cols)}) FROM STDIN") as copy:
        for row in rows:
            copy.write_row(tuple(row[c] for c in cols))


def _count(cur: psycopg.Cursor[Any], table: str) -> int:
    return int(cur.execute(f"SELECT count(*) FROM {table}").fetchone()[0])  # type: ignore[index]


def check_shrink(table: str, current: int, staged: int, min_share: float = MIN_SHARE) -> None:
    if current and staged < current * min_share:
        raise ValueError(
            f"{table}: {staged} rows staged against {current} stored; refusing to replace"
        )


def _set(cols: Sequence[str], key: Sequence[str]) -> str:
    return ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in key)


def _changed(table: str, cols: Sequence[str], key: Sequence[str]) -> str:
    rest = [c for c in cols if c not in key]
    return f"({', '.join(f'{table}.{c}' for c in rest)}) IS DISTINCT FROM " + (
        f"({', '.join(f'EXCLUDED.{c}' for c in rest)})"
    )


def replace_all(conn: psycopg.Connection, rows: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    """Makes the `ref` tables equal to `rows` in the connection's transaction. Returns the number
    of rows inserted, updated or deleted per table."""
    changes: dict[str, int] = {}
    with conn.cursor() as cur:
        _stage(
            cur,
            "stage_airports",
            f"SELECT {', '.join(AIRPORT_COLS)} FROM ref.airports WITH NO DATA",
            AIRPORT_COLS,
            rows["airports"],
        )
        _stage(
            cur,
            "stage_runways",
            "SELECT * FROM ref.runways WITH NO DATA",
            RUNWAY_COLS,
            rows["runways"],
        )
        _stage(
            cur,
            "stage_aircraft",
            "SELECT * FROM ref.aircraft WITH NO DATA",
            AIRCRAFT_COLS,
            rows["aircraft"],
        )
        _stage(
            cur,
            "stage_airlines",
            "SELECT * FROM ref.airlines WITH NO DATA",
            AIRLINE_COLS,
            rows["airlines"],
        )
        _stage(
            cur,
            "stage_countries",
            "SELECT iso_a2, name, ''::text AS geojson FROM ref.countries WITH NO DATA",
            COUNTRY_COLS,
            rows["countries"],
        )
        for table in ("airports", "runways", "aircraft", "airlines", "countries"):
            check_shrink(table, _count(cur, f"ref.{table}"), _count(cur, f"stage_{table}"))

        # Deletes first, children before parents (runways → airports, h3 → countries).
        cur.execute(
            "DELETE FROM ref.runways t WHERE NOT EXISTS (SELECT 1 FROM stage_runways s"
            " WHERE s.airport_icao = t.airport_icao AND s.le_ident = t.le_ident)"
        )
        changes["runways"] = cur.rowcount
        cur.execute("DELETE FROM ref.h3_r4_country")
        for table, key in (
            ("airports", "icao"),
            ("aircraft", "icao24"),
            ("airlines", "icao"),
            ("countries", "iso_a2"),
        ):
            cur.execute(
                f"DELETE FROM ref.{table} t WHERE NOT EXISTS"
                f" (SELECT 1 FROM stage_{table} s WHERE s.{key} = t.{key})"
            )
            changes[table] = cur.rowcount

        cur.execute(
            f"INSERT INTO ref.airports ({', '.join(AIRPORT_COLS)}, geom)"
            f" SELECT {', '.join(AIRPORT_COLS)},"
            " ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography FROM stage_airports"
            f" ON CONFLICT (icao) DO UPDATE SET {_set(AIRPORT_COLS, ['icao'])},"
            " geom = EXCLUDED.geom"
            f" WHERE {_changed('ref.airports', AIRPORT_COLS, ['icao'])}"
        )
        changes["airports"] += cur.rowcount
        for table, cols, key in (
            ("runways", RUNWAY_COLS, ["airport_icao", "le_ident"]),
            ("aircraft", AIRCRAFT_COLS, ["icao24"]),
            ("airlines", AIRLINE_COLS, ["icao"]),
        ):
            cur.execute(
                f"INSERT INTO ref.{table} ({', '.join(cols)}) SELECT {', '.join(cols)}"
                f" FROM stage_{table} ON CONFLICT ({', '.join(key)}) DO UPDATE SET"
                f" {_set(cols, key)} WHERE {_changed(f'ref.{table}', cols, key)}"
            )
            changes[table] += cur.rowcount
        cur.execute(
            "INSERT INTO ref.countries (iso_a2, name, geom)"
            " SELECT iso_a2, name, ST_Multi(ST_CollectionExtract(ST_MakeValid("
            "ST_SetSRID(ST_GeomFromGeoJSON(geojson), 4326)), 3))::geography FROM stage_countries"
            " ON CONFLICT (iso_a2) DO UPDATE SET name = EXCLUDED.name, geom = EXCLUDED.geom"
            " WHERE ref.countries.name IS DISTINCT FROM EXCLUDED.name"
            " OR ST_AsBinary(ref.countries.geom) IS DISTINCT FROM ST_AsBinary(EXCLUDED.geom)"
        )
        changes["countries"] += cur.rowcount
        changes["h3_r4_country"] = refresh_h3_country(cur)
    return changes


def refresh_h3_country(cur: psycopg.Cursor[Any]) -> int:
    """`ref.h3_r4_country` from scratch: the country containing each r4 cell centre. Cells at sea
    (or in a territory without a code) get no row."""
    cur.execute(
        "CREATE TEMP TABLE stage_cells (h3_r4 bigint, lon double precision,"
        " lat double precision) ON COMMIT DROP"
    )
    with cur.copy("COPY stage_cells (h3_r4, lon, lat) FROM STDIN") as copy:
        for cell in countries.r4_cell_centres():
            copy.write_row(cell)
    # Small pieces make each point-in-polygon test cheap.
    cur.execute(
        "CREATE TEMP TABLE stage_country_parts ON COMMIT DROP AS"
        " SELECT iso_a2, ST_Subdivide(geom::geometry, 256) AS g FROM ref.countries"
    )
    cur.execute("CREATE INDEX ON stage_country_parts USING gist (g)")
    cur.execute(
        "INSERT INTO ref.h3_r4_country (h3_r4, iso_a2)"
        " SELECT DISTINCT ON (c.h3_r4) c.h3_r4, p.iso_a2 FROM stage_cells c"
        " JOIN stage_country_parts p"
        " ON ST_Intersects(p.g, ST_SetSRID(ST_MakePoint(c.lon, c.lat), 4326))"
        " ORDER BY c.h3_r4, p.iso_a2"
    )
    return cur.rowcount


@op
def ref_refresh_op(context: OpExecutionContext) -> None:
    settings = JobsSettings()
    now = datetime.now(UTC)
    with recorded_run(settings, "ref_refresh", now, now) as run:
        rows, snapshot = load_sources(Sources(settings.ref_source_dir))
        parsed = ", ".join(f"{len(v)} {k}" for k, v in rows.items())
        context.log.info(f"parsed {parsed} (aircraft from {snapshot})")
        changes = replace_all(run.conn, rows)
        run.rows_out = sum(v for k, v in changes.items() if k != "h3_r4_country")
    context.log.info(f"rows changed: {changes}")


@job(description="Monthly full reload of ref.* (except callsign_routes) and H3 r4 → country.")
def ref_refresh() -> None:
    ref_refresh_op()


@schedule(
    job=ref_refresh,
    cron_schedule="0 1 1 * *",
    execution_timezone="UTC",
    default_status=DefaultScheduleStatus.RUNNING,
)
def ref_refresh_schedule(context: ScheduleEvaluationContext) -> RunRequest:
    tick = context.scheduled_execution_time or datetime.now(UTC)
    return RunRequest(run_key=tick.astimezone(UTC).isoformat())
