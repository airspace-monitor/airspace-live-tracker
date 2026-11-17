-- migrate:up
-- M1.21, step 2 of 2: nothing reads offset_seconds any more (20261117120000). The view selects
-- it, so it is recreated without it, with the same grants.
DROP VIEW ops.v_collectors;
ALTER TABLE ops.collectors DROP COLUMN offset_seconds;
CREATE VIEW ops.v_collectors AS
  SELECT collector_id, owner, created_at, disabled_at FROM ops.collectors;
GRANT SELECT ON ops.v_collectors TO app_reader, grafana_reader, jobs;

-- migrate:down
