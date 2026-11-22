-- migrate:up
-- The stream-worker may only SELECT and UPDATE its progress row, so the row is created here.
-- `-infinity`: a fresh worker processes every live snapshot (docs/04-pipelines.md#p3--stream-worker).
INSERT INTO ops.stream_state (id, last_snapshot_time) VALUES (true, '-infinity')
ON CONFLICT (id) DO NOTHING;

-- migrate:down
