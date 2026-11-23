-- migrate:up
-- MK.4 (docs/03-data-model.md#ops-operations, docs/adr/0006-carbon-aware-operations.md).
-- The carbon intensity the system saw from carbon-signal, one row per 5-minute tick, written by
-- the carbon_readings_record job. A replayed tick keeps its first reading: an override that was
-- active then may be gone now, so the row records what the system actually saw.
CREATE TABLE ops.carbon_readings (
  ts              timestamptz PRIMARY KEY,
  intensity_g_kwh real NOT NULL CHECK (intensity_g_kwh > 0),
  source          text NOT NULL CHECK (source IN ('curve', 'override')),
  received_at     timestamptz NOT NULL DEFAULT now()
);

GRANT SELECT, INSERT ON ops.carbon_readings TO jobs;
GRANT SELECT ON ops.carbon_readings TO grafana_reader;

-- migrate:down
