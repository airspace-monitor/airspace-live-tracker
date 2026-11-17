-- migrate:up
-- M1.10 (docs/03-data-model.md#agg-aggregates). Created empty; history is materialised by
-- agg_backfill_refresh or a manual refresh, and the policy keeps the last 2 h current.

-- Traffic density per H3 cell per 15 minutes (airborne only). Created as jobs, which must own it
-- to call refresh_continuous_aggregate. ALTER ... OWNER TO jobs afterwards fails: the new owner
-- would need CREATE on _timescaledb_internal, which only a superuser can grant.
SET ROLE jobs;
CREATE MATERIALIZED VIEW agg.traffic_h3_15m
WITH (timescaledb.continuous, timescaledb.materialized_only = true) AS
SELECT time_bucket('15 minutes', snapshot_time) AS bucket,
       h3_r4,
       count(*)                                      AS n_obs,
       avg(baro_altitude_m)                          AS avg_alt_m,
       count(*) FILTER (WHERE vertical_rate_ms < -2) AS n_descending
FROM raw.state_vectors
WHERE h3_r4 IS NOT NULL AND NOT on_ground
GROUP BY 1, 2
WITH NO DATA;

SELECT add_continuous_aggregate_policy('agg.traffic_h3_15m',
  start_offset => interval '2 hours', end_offset => interval '15 minutes',
  schedule_interval => interval '5 minutes');
GRANT SELECT ON agg.traffic_h3_15m TO app_reader, grafana_reader;
RESET ROLE;

-- Successful global snapshots per 15 minutes
CREATE VIEW agg.coverage_15m AS
SELECT time_bucket('15 minutes', snapshot_time) AS bucket,
       count(DISTINCT snapshot_time)            AS n_global_snapshots
FROM ops.ingest_batches
WHERE query_kind = 'states_global' AND http_status = 200
GROUP BY 1;

GRANT SELECT ON agg.coverage_15m TO app_reader, grafana_reader, jobs;

-- migrate:down
