#!/bin/bash
# Applies all migrations to a throwaway database and runs db/tests. Never touches the real data volume.
set -euo pipefail
cd "$(dirname "$0")"

env_file=$(mktemp)
for var in POSTGRES AIRSPACE_OWNER INGEST_WRITER STREAM_WORKER JOBS APP_READER LLM_READONLY GRAFANA_READER DAGSTER_DB MLFLOW_DB BACKUP; do
  echo "${var}_PASSWORD=test" >> "$env_file"
done
echo "INGEST_HOST_PORT=18000" >> "$env_file"  # the real ingest-api may be using 8000
echo "DAGSTER_HOST_PORT=13000" >> "$env_file"
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

# Dagster: the webserver loads the `airspace` code location from dagster-code.
dc build dagster-code
dc up -d --wait dagster-code dagster-webserver dagster-daemon
dc exec -T dagster-webserver python - < ../services/orchestrator/tests/smoke_webserver.py

# Backup and restore drill: dump without raw chunk data, restore into a new database, compare.
dc exec -T dagster-code dagster job execute -m orchestrator.definitions -j backup
dc exec -T dagster-code sh -c 'cat /tmp/r2/airspace-backup/*/airspace.dump'   | dc exec -T db sh -c 'cat > /tmp/airspace.dump'
dc exec -T db sh -c 'psql -U postgres -q -v ON_ERROR_STOP=1 -c "CREATE DATABASE restore_drill"   && psql -U postgres -d restore_drill -q -v ON_ERROR_STOP=1        -c "CREATE EXTENSION IF NOT EXISTS timescaledb" -c "SELECT timescaledb_pre_restore()" >/dev/null   && pg_restore -U postgres -d restore_drill --no-owner /tmp/airspace.dump   && psql -U postgres -d restore_drill -q -c "SELECT timescaledb_post_restore()" >/dev/null'
dc exec -T db psql -U postgres -d restore_drill -v ON_ERROR_STOP=1 -q <<'SQL'
DO $$
BEGIN
  IF (SELECT count(*) FROM raw.state_vectors) <> 0 THEN
    RAISE EXCEPTION 'raw chunk data was not excluded from the backup';
  END IF;
  IF (SELECT count(*) FROM ops.collectors) < 2 OR (SELECT count(*) FROM ops.ingest_batches) = 0 THEN
    RAISE EXCEPTION 'restored backup lost ops data';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM timescaledb_information.hypertables
                 WHERE hypertable_schema = 'raw' AND hypertable_name = 'state_vectors') THEN
    RAISE EXCEPTION 'raw.state_vectors is not a hypertable after restore';
  END IF;
END $$;
SQL
echo "backup and restore drill passed"

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
