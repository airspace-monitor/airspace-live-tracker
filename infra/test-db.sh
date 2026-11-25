#!/bin/bash
# Applies all migrations to a throwaway database and runs db/tests. Never touches the real data volume.
set -euo pipefail
cd "$(dirname "$0")"

env_file=$(mktemp)
for var in POSTGRES AIRSPACE_OWNER INGEST_WRITER STREAM_WORKER JOBS APP_READER LLM_READONLY GRAFANA_READER DAGSTER_DB MLFLOW_DB BACKUP GRAFANA_ADMIN; do
  echo "${var}_PASSWORD=test" >> "$env_file"
done
echo "INGEST_HOST_PORT=18000" >> "$env_file"  # the real ingest-api may be using 8000
echo "DAGSTER_HOST_PORT=13000" >> "$env_file"
echo "API_HOST_PORT=18001" >> "$env_file"
echo "GRAFANA_HOST_PORT=13001" >> "$env_file"
# The backup job writes to a local directory instead of R2.
{ echo "R2_RCLONE_TYPE=local"; echo "BACKUP_BUCKET=/tmp/r2/airspace-backup"; echo "ARCHIVE_BUCKET=/tmp/r2/airspace-archive"; } >> "$env_file"
dc() { docker compose -p airspace-test --env-file "$env_file" -f compose.yml "$@"; }
cleanup() { dc --profile tools down -v --remove-orphans >/dev/null 2>&1; rm -f "$env_file"; }
trap cleanup EXIT

dc up -d --wait db
dc run --rm migrate
# Applying again must be a no-op.
dc run --rm migrate
dc exec -T db psql -U postgres -d airspace -q -f - < ../db/tests/test_schema.sql

dc build ingest-api
dc up -d --wait ingest-api
key=$(dc run --rm -T ingest-admin add-collector --id smoke-01 --owner test)
dc exec -T -e COLLECTOR_KEY="$key" ingest-api python - < ../db/tests/ingest_smoke.py

# public-api: the image starts, turns healthy and answers as app_reader.
dc build public-api
dc up -d --wait public-api
dc exec -T public-api python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8001/api/v1/stats', timeout=10)"
echo "public-api smoke test passed"

# Dagster: the webserver loads the `airspace` code location from dagster-code.
dc build dagster-code
dc up -d --wait dagster-code dagster-webserver dagster-daemon
dc exec -T dagster-webserver python - < ../services/orchestrator/tests/smoke_webserver.py
# The tests below run jobs directly; the daemon's schedules would race them (a gap check firing
# between two inserts records a real gap), so it stops once it has started cleanly.
dc stop dagster-daemon >/dev/null

# collector_gap_check: test-01 succeeds at 12:00 and 12:01:30, misses 12:03:00-12:07:30 (4 slots)
# and succeeds again at 12:09:00. Two runs of the same window give one event and two job_runs rows.
dc exec -T db psql -U postgres -d airspace -q -v ON_ERROR_STOP=1 <<'SQL'
INSERT INTO ops.ingest_batches (batch_id, collector_id, query_kind, requested_at, snapshot_time, http_status) VALUES
  ('00000000-0000-7000-8000-0000000000a1', 'test-01', 'states_global', '2026-10-30 12:01:31Z', '2026-10-30 12:01:30Z', 200),
  ('00000000-0000-7000-8000-0000000000a2', 'test-01', 'states_global', '2026-10-30 12:03:01Z', NULL, 0),
  ('00000000-0000-7000-8000-0000000000a3', 'test-01', 'states_global', '2026-10-30 12:09:02Z', '2026-10-30 12:09:00Z', 200);
SQL
gap_config='{"ops": {"collector_gap_check_op": {"config": {"window_start": "2026-10-30T12:00:00+00:00", "window_end": "2026-10-30T12:10:30+00:00"}}}}'
echo "$gap_config" | dc exec -T dagster-code sh -c 'cat > /tmp/gap_window.yaml'  # JSON is YAML
for _ in 1 2; do
  dc exec -T dagster-code dagster job execute -m orchestrator.definitions -j collector_gap_check \
    -c /tmp/gap_window.yaml >/dev/null
done
dc exec -T db psql -U postgres -d airspace -v ON_ERROR_STOP=1 -q <<'SQL'
DO $$
BEGIN
  -- The daemon's own schedule may also run during the test, so only this window is checked.
  IF (SELECT array_agg(dedupe_key) FROM core.events WHERE dedupe_key LIKE 'collector_gap:test-01:%'
        AND ts >= '2026-10-30 12:00Z' AND ts < '2026-10-30 12:10:30Z')
     IS DISTINCT FROM ARRAY['collector_gap:test-01:2026-10-30T12:03:00Z'] THEN
    RAISE EXCEPTION 'expected exactly one gap event for test-01 at 12:03:00';
  END IF;
  IF (SELECT count(*) FROM ops.job_runs WHERE job = 'collector_gap_check' AND status = 'ok'
        AND window_start = '2026-10-30 12:00Z' AND window_end = '2026-10-30 12:10:30Z') <> 2 THEN
    RAISE EXCEPTION 'expected two ok collector_gap_check job_runs rows for the test window';
  END IF;
END $$;
SQL
echo "collector_gap_check test passed"

# OurAirports seed (M1.18): load the fixture twice as `jobs`; re-running changes nothing.
for _ in 1 2; do
  dc run --rm -T -v "$(cd .. && pwd)/db:/db:ro" dagster-code \
    python /db/seeds/ourairports.py --from-dir /db/tests/ourairports
done
dc exec -T db psql -U postgres -d airspace -v ON_ERROR_STOP=1 -q <<'SQL'
DO $$
BEGIN
  IF (SELECT array_agg(icao ORDER BY icao) FROM ref.airports) <> ARRAY['LHBP', 'LOAN', 'LOWW', 'LZIB'] THEN
    RAISE EXCEPTION 'unexpected ref.airports rows';
  END IF;
  IF (SELECT array_agg(icao ORDER BY icao) FROM ref.airports WHERE is_target) <> ARRAY['LHBP', 'LOWW', 'LZIB'] THEN
    RAISE EXCEPTION 'target airports not flagged';
  END IF;
  IF (SELECT round(ST_Distance(geom, ST_MakePoint(16.5697, 48.110298)::geography)) FROM ref.airports WHERE icao = 'LOWW') <> 0 THEN
    RAISE EXCEPTION 'LOWW geom does not match lat/lon';
  END IF;
  IF (SELECT count(*) FROM ref.runways) <> 3 THEN
    RAISE EXCEPTION 'expected 3 runways';
  END IF;
END $$;
SQL
echo "ourairports seed test passed"

# ref_refresh (M3.1) from the fixture files. The airports and runways match the seed above, so the
# first run only adds 4 aircraft, 3 airlines and 3 countries; a second run changes nothing; a third
# with one aircraft gone upstream deletes it. H3 cells get the fixture countries only.
ref_run() {  # $1 = source dir, $2 = optional shell setup run first
  dc run --rm -T -v "$(cd .. && pwd)/db:/db:ro" -e REF_SOURCE_DIR="$1" dagster-code \
    sh -c "${2:-true} && dagster job execute -m orchestrator.definitions -j ref_refresh >/dev/null"
}
ref_run /db/tests/refdata
ref_run /db/tests/refdata
ref_run /tmp/ref "cp -r /db/tests/refdata /tmp/ref && sed -i '/^.4b1805/d' /tmp/ref/aircraft.csv"
dc exec -T db psql -U postgres -d airspace -v ON_ERROR_STOP=1 -q <<'SQL'
DO $$
BEGIN
  IF (SELECT array_agg(rows_out ORDER BY run_id) FROM ops.job_runs WHERE job = 'ref_refresh' AND status = 'ok')
     IS DISTINCT FROM ARRAY[10, 0, 1] THEN
    RAISE EXCEPTION 'expected ref_refresh runs changing 10, 0, then 1 rows';
  END IF;
  IF (SELECT array_agg(icao24 ORDER BY icao24) FROM ref.aircraft) IS DISTINCT FROM ARRAY['000000', '3b7d41', '440017'] THEN
    RAISE EXCEPTION 'unexpected ref.aircraft rows';
  END IF;
  IF (SELECT (registration, operator_icao)::text FROM ref.aircraft WHERE icao24 = '440017') <> '(OE-LBM,AUA)' THEN
    RAISE EXCEPTION 'the latest aircraft row did not win';
  END IF;
  IF (SELECT array_agg(icao ORDER BY icao) FROM ref.airlines) IS DISTINCT FROM ARRAY['AUA', 'DLH', 'SWR'] THEN
    RAISE EXCEPTION 'unexpected ref.airlines rows';
  END IF;
  IF (SELECT array_agg(iso_a2 ORDER BY iso_a2) FROM ref.countries) IS DISTINCT FROM ARRAY['AT', 'FR', 'SK'] THEN
    RAISE EXCEPTION 'unexpected ref.countries rows';
  END IF;
  IF NOT (SELECT ST_Covers(geom, ST_MakePoint(16.5697, 48.110298)::geography) FROM ref.countries WHERE iso_a2 = 'AT') THEN
    RAISE EXCEPTION 'LOWW is not inside the AT fixture polygon';
  END IF;
  IF (SELECT array_agg(DISTINCT iso_a2 ORDER BY iso_a2) FROM ref.h3_r4_country) IS DISTINCT FROM ARRAY['AT', 'FR', 'SK'] THEN
    RAISE EXCEPTION 'h3_r4_country should only map cells to the fixture countries';
  END IF;
  IF (SELECT count(*) FROM ref.h3_r4_country WHERE iso_a2 = 'AT') < 20 THEN
    RAISE EXCEPTION 'too few AT cells in h3_r4_country';
  END IF;
  IF (SELECT count(*) FROM ref.airports WHERE is_target) <> 3 OR (SELECT count(*) FROM ref.runways) <> 3 THEN
    RAISE EXCEPTION 'airports or runways changed';
  END IF;
END $$;
SQL
echo "ref_refresh test passed"

# stream-worker (M2.2): live snapshots relative to now, announced with NOTIFY as ingest does.
# e00001 squawks 7700 over Hungary 4 times (one event, keyed by its first observation); e00002
# squawks outside the Europe box and e00003 only twice (no events, D14); e00004 descends and
# then climbs near LOWW (one go-around, not a second one for the continued climb). The ingest
# smoke test's live snapshot may be newer than these, so the progress row is reset first.
dc build stream-worker
dc up -d --wait stream-worker
dc exec -T db psql -U postgres -d airspace -q -v ON_ERROR_STOP=1 <<'SQL'
BEGIN;
UPDATE ops.stream_state SET last_snapshot_time = '-infinity';
WITH t AS (SELECT k, date_trunc('second', now()) - (6 - k) * interval '60 seconds' AS ts
           FROM generate_series(0, 5) k)
INSERT INTO raw.state_vectors (snapshot_time, icao24, batch_id, time_position, lat, lon,
                               baro_altitude_m, on_ground, vertical_rate_ms, squawk, callsign)
SELECT t.ts, a.icao24, '00000000-0000-7000-8000-0000000000c1', t.ts, a.lat, a.lon, a.alt, false,
       a.vr, a.squawk, a.callsign
FROM t JOIN (VALUES
  ('e00001', 0, 47.5, 19.0, 9000, 0, '7700', 'WZZ1'), ('e00001', 1, 47.5, 19.1, 9000, 0, '7700', 'WZZ1'),
  ('e00001', 2, 47.5, 19.2, 9000, 0, '7700', 'WZZ1'), ('e00001', 3, 47.5, 19.3, 9000, 0, '7700', 'WZZ1'),
  ('e00002', 0, 30.0, 19.0, 9000, 0, '7700', 'XYZ2'), ('e00002', 1, 30.0, 19.1, 9000, 0, '7700', 'XYZ2'),
  ('e00002', 2, 30.0, 19.2, 9000, 0, '7700', 'XYZ2'), ('e00002', 3, 30.0, 19.3, 9000, 0, '7700', 'XYZ2'),
  ('e00003', 2, 47.6, 19.5, 9000, 0, '7600', 'WZZ3'), ('e00003', 3, 47.6, 19.6, 9000, 0, '7600', 'WZZ3'),
  ('e00004', 1, 48.13, 16.60, 600, -1, '1000', 'AUA478'), ('e00004', 2, 48.13, 16.60, 400, -4, '1000', 'AUA478'),
  ('e00004', 3, 48.13, 16.61, 450, 6, '1000', 'AUA478'), ('e00004', 4, 48.14, 16.62, 600, 7, '1000', 'AUA478'),
  ('e00005', 5, 47.0, 18.0, 10000, 0, '2000', 'WZZ5')
) AS a(icao24, k, lat, lon, alt, vr, squawk, callsign) USING (k);
NOTIFY new_snapshot;
COMMIT;
SQL
stream_events() {
  dc exec -T db psql -U postgres -d airspace -A -t -c \
    "SELECT string_agg(kind || ':' || icao24, ',' ORDER BY kind, icao24) FROM core.events WHERE icao24 LIKE 'e0000%'"
}
for _ in $(seq 30); do
  [ "$(stream_events)" = "go_around:e00004,squawk_7700:e00001" ] && break
  sleep 1
done
[ "$(stream_events)" = "go_around:e00004,squawk_7700:e00001" ] || dc logs stream-worker | tail -30
dc exec -T stream-worker python -m stream --once >/dev/null
dc exec -T db psql -U postgres -d airspace -v ON_ERROR_STOP=1 -q <<'SQL'
DO $$
DECLARE first_obs timestamptz := (SELECT min(snapshot_time) FROM raw.state_vectors WHERE icao24 = 'e00001');
BEGIN
  IF (SELECT array_agg(dedupe_key ORDER BY dedupe_key) FROM core.events WHERE icao24 LIKE 'e0000%')
     IS DISTINCT FROM ARRAY[
       'go_around:e00004:' || to_char((SELECT snapshot_time FROM raw.state_vectors WHERE icao24 = 'e00004' AND vertical_rate_ms = 6) AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
       'squawk_7700:e00001:' || to_char(first_obs AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')] THEN
    RAISE EXCEPTION 'unexpected stream events: %',
      (SELECT array_agg(dedupe_key) FROM core.events WHERE icao24 LIKE 'e0000%');
  END IF;
  IF (SELECT title FROM core.events WHERE kind = 'go_around' AND icao24 = 'e00004') <> 'Go-around at LOWW (AUA478)' THEN
    RAISE EXCEPTION 'unexpected go-around title';
  END IF;
  IF (SELECT last_snapshot_time FROM ops.stream_state)
     < (SELECT max(snapshot_time) FROM raw.state_vectors WHERE icao24 LIKE 'e0000%') THEN
    RAISE EXCEPTION 'ops.stream_state did not advance to the newest snapshot';
  END IF;
END $$;
SQL
echo "stream-worker test passed"

# Aggregates (M1.10): a batch received now for 2026-10-29 10:00 is late, so agg_backfill_refresh
# materialises that day. Only airborne rows with an H3 cell count; app_reader can read the result.
dc exec -T db psql -U postgres -d airspace -q -v ON_ERROR_STOP=1 <<'SQL'
INSERT INTO ops.ingest_batches (batch_id, collector_id, query_kind, requested_at, snapshot_time, http_status)
VALUES ('00000000-0000-7000-8000-0000000000b1', 'test-01', 'states_global', '2026-10-29 10:00:01Z', '2026-10-29 10:00:00Z', 200);
INSERT INTO raw.state_vectors (snapshot_time, icao24, batch_id, h3_r4, on_ground, baro_altitude_m, vertical_rate_ms) VALUES
  ('2026-10-29 10:00Z', 'a00001', '00000000-0000-7000-8000-0000000000b1', 595183493020581887, false, 10000, -5),
  ('2026-10-29 10:00Z', 'a00002', '00000000-0000-7000-8000-0000000000b1', 595183493020581887, false, 8000, 0),
  ('2026-10-29 10:00Z', 'a00003', '00000000-0000-7000-8000-0000000000b1', 595183493020581887, true, 200, 0),
  ('2026-10-29 10:00Z', 'a00004', '00000000-0000-7000-8000-0000000000b1', NULL, false, 9000, 0);
SQL
agg_window="{\"ops\": {\"agg_backfill_refresh_op\": {\"config\": {\"window_start\": \"$(date -u -d '-1 hour' +%FT%T+00:00)\", \"window_end\": \"$(date -u -d '+1 minute' +%FT%T+00:00)\"}}}}"
echo "$agg_window" | dc exec -T dagster-code sh -c 'cat > /tmp/agg_window.yaml'
dc exec -T dagster-code dagster job execute -m orchestrator.definitions -j agg_backfill_refresh \
  -c /tmp/agg_window.yaml >/dev/null
dc exec -T db psql -U postgres -d airspace -v ON_ERROR_STOP=1 -q <<'SQL'
DO $$
DECLARE r record;
BEGIN
  SELECT * INTO r FROM agg.traffic_h3_15m WHERE bucket = '2026-10-29 10:00Z';
  IF r IS NULL OR r.n_obs <> 2 OR r.avg_alt_m <> 9000 OR r.n_descending <> 1 THEN
    RAISE EXCEPTION 'unexpected agg.traffic_h3_15m row: %', r;
  END IF;
  IF (SELECT n_global_snapshots FROM agg.coverage_15m WHERE bucket = '2026-10-29 10:00Z') <> 1 THEN
    RAISE EXCEPTION 'agg.coverage_15m should count one snapshot';
  END IF;
  IF EXISTS (SELECT 1 FROM ops.job_runs WHERE job = 'agg_backfill_refresh' AND status <> 'ok') THEN
    RAISE EXCEPTION 'agg_backfill_refresh did not finish ok';
  END IF;
END $$;
SET ROLE app_reader;
SELECT count(*) FROM agg.traffic_h3_15m;
SELECT count(*) FROM agg.coverage_15m;
RESET ROLE;
SQL
echo "aggregates test passed"

# carbon_readings_record (MK.4): with a demo override set on carbon-signal, a run stores the
# override; replaying the window after the override is cleared keeps the first reading.
dc build carbon-signal
dc up -d --wait carbon-signal
signal() { dc exec -T carbon-signal python -c "import sys, urllib.request as u; r = u.Request('http://127.0.0.1:8002/v1/override', data=sys.argv[2].encode() or None, method=sys.argv[1], headers={'Content-Type': 'application/json'}); u.urlopen(r, timeout=5)" "$@"; }
signal PUT '{"intensity_g_kwh": 420}'
now_s=$(date -u +%s)
carbon_window="{\"ops\": {\"carbon_readings_record_op\": {\"config\": {\"window_start\": \"$(date -u -d "@$((now_s - 300))" +%FT%T+00:00)\", \"window_end\": \"$(date -u -d "@$now_s" +%FT%T+00:00)\"}}}}"
echo "$carbon_window" | dc exec -T dagster-code sh -c 'cat > /tmp/carbon_window.yaml'
dc exec -T dagster-code dagster job execute -m orchestrator.definitions -j carbon_readings_record \
  -c /tmp/carbon_window.yaml >/dev/null
signal DELETE ''
dc exec -T dagster-code dagster job execute -m orchestrator.definitions -j carbon_readings_record \
  -c /tmp/carbon_window.yaml >/dev/null
dc exec -T db psql -U postgres -d airspace -v ON_ERROR_STOP=1 -q <<'SQL'
DO $$
BEGIN
  IF (SELECT array_agg((intensity_g_kwh, source)::text) FROM ops.carbon_readings)
     IS DISTINCT FROM ARRAY['(420,override)'] THEN
    RAISE EXCEPTION 'expected one override reading of 420';
  END IF;
  IF (SELECT count(*) FROM ops.job_runs WHERE job = 'carbon_readings_record' AND status = 'ok') <> 2 THEN
    RAISE EXCEPTION 'expected two ok carbon_readings_record runs';
  END IF;
END $$;
SQL
echo "carbon_readings_record test passed"

# metar_fetch (M2.3) against a local stand-in for aviationweather.gov (a static file; the query is
# ignored). Only target stations inside the window are stored; a replay writes nothing; a corrected
# report replaces the stored one.
metar_fixture() {  # $1 = window end (unix s), $2 = LOWW raw text
  dc exec -T dagster-code python - "$1" "$2" <<'PY'
import json, os, sys
end, loww = int(sys.argv[1]), sys.argv[2]
rec = lambda icao, t, raw: {"icaoId": icao, "obsTime": t, "rawOb": raw, "wdir": 100, "wspd": 7,
    "temp": 2, "dewp": -4, "altim": 1018, "clouds": [{"cover": "BKN", "base": 3000}], "fltCat": "MVFR"}
records = [
    rec("LOWW", end - 1800, loww),
    rec("LZIB", end - 3600, "METAR LZIB 0000Z 08011KT 0800 FG BKN030 02/M03 Q1020"),
    rec("EDDM", end - 1800, "METAR EDDM 0000Z 10007KT 9999 BKN030 02/M04 Q1018"),  # not a target
    rec("LOWW", end - 4 * 3600, loww),                                               # before the window
]
os.makedirs("/tmp/metar", exist_ok=True)
json.dump(records, open("/tmp/metar/metar.json", "w"))
PY
}
now_s=$(date -u +%s)
metar_window="{\"ops\": {\"metar_fetch_op\": {\"config\": {\"window_start\": \"$(date -u -d "@$((now_s - 10800))" +%FT%T+00:00)\", \"window_end\": \"$(date -u -d "@$now_s" +%FT%T+00:00)\"}}}}"
echo "$metar_window" | dc exec -T dagster-code sh -c 'cat > /tmp/metar_window.yaml'
metar_run() {
  dc exec -T -e METAR_URL=http://127.0.0.1:8765/metar.json dagster-code \
    dagster job execute -m orchestrator.definitions -j metar_fetch -c /tmp/metar_window.yaml >/dev/null
}
metar_fixture "$now_s" "METAR LOWW 0000Z 10007KT 9999 BKN030 02/M04 Q1018"
dc exec -d dagster-code python -m http.server 8765 --bind 127.0.0.1 --directory /tmp/metar
metar_run
metar_run
metar_fixture "$now_s" "METAR COR LOWW 0000Z 10007KT 9999 BKN030 02/M04 Q1018"
metar_run
dc exec -T db psql -U postgres -d airspace -v ON_ERROR_STOP=1 -q <<'SQL'
DO $$
BEGIN
  IF (SELECT array_agg(station ORDER BY station) FROM core.metar) IS DISTINCT FROM ARRAY['LOWW', 'LZIB'] THEN
    RAISE EXCEPTION 'expected one LOWW and one LZIB report';
  END IF;
  IF (SELECT raw_text FROM core.metar WHERE station = 'LOWW') NOT LIKE 'METAR COR %' THEN
    RAISE EXCEPTION 'the corrected LOWW report did not replace the first one';
  END IF;
  IF (SELECT (visibility_m, ceiling_m, wind_speed_ms, flight_category)::text FROM core.metar WHERE station = 'LZIB')
     IS DISTINCT FROM '(800,914,3.6,MVFR)' THEN
    RAISE EXCEPTION 'LZIB not stored in SI units';
  END IF;
  IF (SELECT array_agg(rows_out ORDER BY run_id) FROM ops.job_runs WHERE job = 'metar_fetch' AND status = 'ok')
     IS DISTINCT FROM ARRAY[2, 0, 1] THEN
    RAISE EXCEPTION 'expected metar_fetch runs writing 2, 0, then 1 rows';
  END IF;
END $$;
SQL
echo "metar_fetch test passed"

# Backup and restore drill (after the aggregates test, so agg.traffic_h3_15m has data): dump without
# raw chunk data or continuous-aggregate data (D13), restore into a new database, compare, then
# check that the aggregate is rebuilt once raw data is back.
dc exec -T dagster-code dagster job execute -m orchestrator.definitions -j backup
dc exec -T dagster-code sh -c 'cat /tmp/r2/airspace-backup/*/airspace.dump'   | dc exec -T db sh -c 'cat > /tmp/airspace.dump'
dc exec -T db sh -c 'psql -U postgres -q -v ON_ERROR_STOP=1 -c "CREATE DATABASE restore_drill"   && psql -U postgres -d restore_drill -q -v ON_ERROR_STOP=1        -c "CREATE EXTENSION IF NOT EXISTS timescaledb" -c "SELECT timescaledb_pre_restore()" >/dev/null   && pg_restore -U postgres -d restore_drill --no-owner /tmp/airspace.dump   && psql -U postgres -d restore_drill -q -c "SELECT timescaledb_post_restore()" >/dev/null'
dc exec -T db psql -U postgres -d restore_drill -v ON_ERROR_STOP=1 -q <<'SQL'
DO $$
BEGIN
  IF (SELECT count(*) FROM raw.state_vectors) <> 0 THEN
    RAISE EXCEPTION 'raw chunk data was not excluded from the backup';
  END IF;
  IF (SELECT count(*) FROM agg.traffic_h3_15m) <> 0 THEN
    RAISE EXCEPTION 'continuous-aggregate data was not excluded from the backup';
  END IF;
  IF (SELECT count(*) FROM ops.collectors) < 2 OR (SELECT count(*) FROM ops.ingest_batches) = 0 THEN
    RAISE EXCEPTION 'restored backup lost ops data';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM timescaledb_information.hypertables
                 WHERE hypertable_schema = 'raw' AND hypertable_name = 'state_vectors') THEN
    RAISE EXCEPTION 'raw.state_vectors is not a hypertable after restore';
  END IF;
END $$;
-- What a replay from the archives does: raw rows come back, then the aggregate is refreshed.
INSERT INTO raw.state_vectors (snapshot_time, icao24, batch_id, h3_r4, on_ground, baro_altitude_m, vertical_rate_ms)
VALUES ('2026-10-29 10:00Z', 'a00001', '00000000-0000-7000-8000-0000000000b1', 595183493020581887, false, 10000, -5);
CALL refresh_continuous_aggregate('agg.traffic_h3_15m', '2026-10-29', '2026-10-30');
DO $$
BEGIN
  IF (SELECT n_obs FROM agg.traffic_h3_15m WHERE bucket = '2026-10-29 10:00Z') IS DISTINCT FROM 1 THEN
    RAISE EXCEPTION 'agg.traffic_h3_15m was not rebuilt from restored raw data';
  END IF;
END $$;
SQL
echo "backup and restore drill passed"

# Grafana (M1.13): every panel query runs as grafana_reader, the provisioned datasource connects
# and the ops dashboard is loaded.
python3 ../infra/grafana/check_queries.py ../infra/grafana/dashboards/*.json \
  | dc exec -T db psql -U grafana_reader -d airspace -v ON_ERROR_STOP=1 -q >/dev/null
dc up -d --wait grafana
dc exec -T grafana wget -q -O - http://admin:test@127.0.0.1:3000/api/datasources/uid/airspace/health \
  | grep -q '"status":"OK"' || { echo "grafana datasource is not healthy"; exit 1; }
dc exec -T grafana wget -q -O - "http://admin:test@127.0.0.1:3000/api/search?query=Airspace%20ops" \
  | grep -q '"uid":"airspace-ops"' || { echo "ops dashboard not provisioned"; exit 1; }
dc exec -T grafana wget -q -O - "http://admin:test@127.0.0.1:3000/api/search?query=Airspace%20sustainability" \
  | grep -q '"uid":"airspace-sustainability"' || { echo "sustainability dashboard not provisioned"; exit 1; }
echo "grafana test passed"
