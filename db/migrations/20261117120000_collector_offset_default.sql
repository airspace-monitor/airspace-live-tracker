-- migrate:up
-- M1.21, step 1 of 2: code no longer writes offset_seconds (one collector on a plain 90 s grid,
-- D4). A default keeps inserts from new code working; the next migration drops the column.
ALTER TABLE ops.collectors ALTER COLUMN offset_seconds SET DEFAULT 0;

-- migrate:down
