# 04 · Pipelines

```mermaid
flowchart TB
  subgraph P1["P1 Collector (home)"]
    T["slot tick every 90 s"] --> F["GET /states/all"]
    FL["daily 06:00 UTC"] --> FA["GET /flights/all (yesterday, 12 windows)"]
    F --> W["spool/pending/&lt;batch_id&gt;.json.gz"]
    FA --> W
    W --> U["uploader → POST /ingest/v1/batches"]
    U -->|"2xx"| M["spool/sent/"]
    U -->|"422"| RJ["spool/rejected/"]
    M --> D["00:30 UTC compaction → spool/archive/*.parquet → R2 upload"]
  end
  subgraph P2["P2 Ingest (server)"]
    V["validate + normalise + h3"] --> I["INSERT … ON CONFLICT DO NOTHING"]
    I --> B["ops.ingest_batches"] --> N["NOTIFY new_snapshot (live batches only)"]
  end
  subgraph P3["P3 Stream worker"]
    N --> E["squawk + go-around events"]
    N --> ETA["ETA inference"]
  end
  subgraph P4["P4 Orchestrator (Dagster)"]
    SES["flights_sessionizer"] --> DEST["destination_inference"]
    CAGG["refresh bucket"] --> AN["anomaly_scoring"]
    OTHER["metar · baselines · briefing · training · DQ · backup"]
  end
  U --> V
```

## Shared definitions

These live in `libs/airspace_common` and are used by every pipeline and by model training, so serving and training compute features the same way.

- **Live window:** `LIVE_WINDOW_SECONDS = 600`. A snapshot is *live* when `snapshot_time ≥ now() − 600 s`. Only live snapshots reach the map stream, the stream-worker and the event feed in real time.
- **Latest snapshot:** the `states_global` batch with `http_status = 200` and the greatest `snapshot_time`.
- **Height above an airport** (`altitude.height_above_airport_m(state, airport, metar)`):
  1. If `baro_altitude_m` is set and the airport has a METAR with `observed_at` within 90 min before the state: `baro_altitude_m + 8.3 × (qnh_hpa − 1013.25) − elevation_m`. Method `qnh`.
  2. Else if `baro_altitude_m` is set: `baro_altitude_m − elevation_m`. Method `uncorrected`.
  3. Else if `geo_altitude_m` is set: `geo_altitude_m − elevation_m`. Method `geo`.
  4. Else: unknown; rules that need a height do not fire.
- **Inbound candidate for an ETA** (target airport A): the aircraft is airborne, has a `flight_id`, is within 400 km great-circle of A, its `true_track_deg` is within 30° of the bearing to A, and either `vertical_rate_ms ≤ −2` in at least one of its last 3 observations or `baro_altitude_m ≤ 7,000`. Overflights cruising above 7,000 m without descending are not candidates. Destination predictions play no part.
- **Watermark** (for finalising flights): `min(now() − 10 min, latest successful snapshot_time)`. While the collector is silent the watermark holds, so an outage never finalises flights as lost before the backlog has arrived.

## P1 · Collector

**Where it runs**
- **Windows PC (2026-10-29 to 11-07, now stopped):** a Python 3.12 process (`uv run -m collector`) registered in Windows Task Scheduler: trigger *At startup*, *Run whether user is logged on or not*, restart every 1 min on failure (999 attempts), no time limit. Windows power plan: never sleep while plugged in. Docker Desktop is not used on Windows because it only starts after a user signs in.
- **Raspberry Pi (since 2026-11-07, [D5](11-tasks.md#decided-while-building)):** runs 24/7 on a 64-bit OS with the arm64 Docker image (`collector/Dockerfile`), Docker Engine and `restart: unless-stopped`: `docker compose -f collector/compose.yml up -d --build` from the repo root, with `.env` there and `spool/` bind-mounted. `~/airspace` is a git checkout of `main`: update with `git pull` and the same command. Its `INGEST_URL` uses the VM's Tailscale IP (`100.80.31.53`), not its name, because Tailscale DNS is off on the Pi (since 2026-11-16).

**State-vector loop**
1. Next slot: `next = ceil(now / CADENCE_SECONDS) × CADENCE_SECONDS`. Sleep until then. The clock is NTP-synced.
2. Ensure a valid OAuth token; refresh when fewer than 60 s of `expires_in` remain.
3. `GET /api/states/all?extended=1`, timeout 20 s.
4. Wrap the result in a batch envelope ([05](05-api-contract.md#post-ingestv1batches)) with a new UUIDv7 `batch_id` (`uuid6.uuid7()`), `requested_at`, status and headers. Write it atomically to `spool/pending/<batch_id>.json.gz` (write `.tmp`, then rename). **The data is safe from this point.** Failed requests are spooled too, with `response = null`.
5. The uploader task sends pending files oldest-first and moves each to `spool/sent/` after a 2xx.

**Flight-list task** (`FLIGHT_LISTS_ENABLED=true`)
1. At 06:00 UTC, for yesterday (UTC), request `GET /api/flights/all?begin=&end=` for 12 two-hour windows `[00:00, 02:00) … [22:00, 24:00)`.
2. Each response becomes one batch with `query_kind = flights_all`, spooled and uploaded like state vectors.
3. HTTP 404 or an empty array means the nightly data is not ready: retry that window every hour until 18:00 UTC, then give up and upload the failed envelope.
4. HTTP 400 for an interval that is too long: split the window into two halves and retry, down to 30-minute windows.
5. The server keeps one copy of each flight (primary key), so fetching a window twice is harmless.

**Failure handling**

| Failure | Behaviour |
|---|---|
| OpenSky 429 | Skip slots until `X-Rate-Limit-Retry-After-Seconds` has passed. Spool the failed envelope with `http_status = 429` and `retry_after_s` |
| OpenSky 5xx or timeout | One retry after 10 s within the same slot, then skip the slot. Spool the failed envelope (`http_status = 0` for a timeout) |
| Token refresh fails | Log, back off 60 s, keep trying; slots are skipped meanwhile and spooled as failed envelopes with `http_status = 0` |
| Ingest unreachable or 5xx | Files stay in `pending/`; exponential backoff from 5 s to 5 min; drain oldest-first on recovery |
| Ingest 401 | Stop uploading, keep spooling, log an ERROR every 5 min, retry one upload every 5 min |
| Ingest 422 | Move the file to `spool/rejected/` and log an ERROR. Never retried automatically |
| OpenSky unreachable for 10 slots in a row (15 min of `http_status = 0`) | The collector exits with an error, and Docker (`restart: unless-stopped`) starts it again. A restart refreshes a stale DNS config: after a reboot on 2026-11-13 the Pi's container kept an empty `resolv.conf` and lost 2.7 days of slots without crashing. With no network at all it restarts every 15 min |
| Collector off | Gap, visible in `ops.ingest_batches`, Grafana and a `collector_gap` event. |
| Clock skew | `snapshot_time` comes from OpenSky. `requested_at` is only used for slot and lag metrics |

**Spool layout:** `spool/pending/`, `spool/sent/`, `spool/rejected/`, `spool/archive/`, plus `spool/state/` (flight-list progress per day, so a restart neither repeats nor skips windows; kept 7 days), `spool/logs/collector.log` (JSON lines, rotated at 10 MB × 5) and `spool/collector.lock` (one collector per spool; a second process refuses to start, because it would double credit use).

**Status:** `uv run -m collector status` prints the pending file count and size and the newest batches.

**Archive:** at 00:30 UTC, compact each finished day of `sent/` state-vector files into `spool/archive/states/YYYY-MM-DD.parquet` and flight-list files into `spool/archive/flights/YYYY-MM-DD.parquet`, then delete those JSON files (`collector/archive.py`):

- A day is compacted only when none of its files are left in `pending/`, so every row has been uploaded. A file's day is the time in its UUIDv7 batch id.
- One row per state vector (or flight) with OpenSky's original fields plus the batch envelope (`batch_id`, `collector_id`, `requested_at`, `credits_remaining`, `snapshot_time` or the flight-list window), so `collector.replay` can rebuild the exact batches. Failed requests have no rows; `ops.ingest_batches` keeps them.
- zstd, one row group per hour, sorted by `icao24` and `snapshot_time` within the hour (a whole-day sort needs more RAM than the Pi has).
- The JSON is deleted only after the archive is fsynced, renamed into place and its row count checked. An existing archive is never overwritten.

Right after the compaction, `rclone copy` puts the archive into Cloudflare R2 `airspace-archive/<collector_id>/` (finished files only; `collector/archive_upload.py`). Local archives older than `ARCHIVE_RETENTION_DAYS` (30) are then deleted, but only those R2 holds at the same size, which keeps about 6 GB on the Pi's SD card ([D6](11-tasks.md#decided-while-building)); if uploads stop working, nothing is deleted. R2 keeps archives until the 8 GB cap, about 5 weeks ([D7](11-tasks.md#decided-while-building)). The Pi's R2 token can only read and write `airspace-archive`. Without `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID` and `R2_SECRET_ACCESS_KEY` the upload and the retention are skipped.

**Spool-only mode:** `UPLOAD_ENABLED=false`, used from M0 before the server exists. When the server is live, set it to `true`; the uploader drains `pending/` (see [Catch-up](#catch-up-after-an-outage-or-the-m0-backlog)).

**Config (env, documented in `.env.example`):**
`COLLECTOR_ID`, `OPENSKY_CLIENT_ID`, `OPENSKY_CLIENT_SECRET`, `INGEST_URL`, `INGEST_API_KEY`, `CADENCE_SECONDS=90`, `SPOOL_DIR`, `UPLOAD_ENABLED=true`, `FLIGHT_LISTS_ENABLED=true`, `ARCHIVE_RETENTION_DAYS=30`, `RCLONE_REMOTE=r2:airspace-archive`, `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`. There is no other cadence or query configuration.

## P2 · Ingest

`POST /ingest/v1/batches` (FastAPI, role `ingest_writer`):
1. Authenticate the bearer key against `ops.collectors.api_key_hash` and check `collector_id` matches. Disabled collectors get 401.
2. If `batch_id` exists in `ops.ingest_batches`, return `200 {"status":"duplicate"}`.
3. Validate the envelope with Pydantic (422 on failure). Normalise each row:
   - `states_global`: trim callsign (empty → NULL), lower-case `icao24`, unix seconds → `timestamptz`; reject rows with lat ∉ [−90, 90], lon ∉ [−180, 180] or a non-hex `icao24`, counting them in `n_rejected`. Compute `h3_r4` where lat/lon are set.
   - `flights_all`: same trimming and casing; reject rows without `icao24`, `firstSeen` or `lastSeen`, or with a non-hex `icao24`.
4. In one transaction:
   - `COPY` the rows into a temp table, then `INSERT INTO raw.state_vectors` (or `raw.opensky_flights`) `… ON CONFLICT DO NOTHING`.
   - Insert the `ops.ingest_batches` row. `snapshot_time` is set only for a successful `states_global` batch.
   - If the batch is a successful `states_global` batch and its snapshot is live: `NOTIFY new_snapshot, '<snapshot_time ISO>'`. Older batches are stored silently.
5. Return `202` with counts.

Target latency: < 1.5 s for a 12k-state batch.

## P3 · Stream worker

Listens on `new_snapshot`. It keeps its progress in `ops.stream_state.last_snapshot_time`. On each notification, and on startup or reconnect, it processes, in order, every live snapshot newer than `last_snapshot_time`, then updates it. Snapshots that are no longer live are never processed; their events are recovered only by a manual `events_rebuild` run.

| Job | Rule | Output |
|---|---|---|
| Squawk events | An *episode* is consecutive qualifying observations of one `icao24` with one `squawk` ∈ {7500, 7600, 7700}, gaps ≤ 30 min. A qualifying observation is airborne (`on_ground` false), has a position, and lies in the Europe box, lat 35–72 and lon −25–45 ([D14](11-tasks.md#decided-while-building)). An episode becomes one event per code once it has 3 qualifying observations; `ts`, key and location use its first observation | `core.events` |
| Go-around | Within 15 km of a target airport; height above the airport < 1,000 m; an observation with `vertical_rate_ms < −2` followed within the next 3 observations by one with `vertical_rate_ms > +2`; no `on_ground` in between. `ts` = the climbing observation's `time_position` | `core.events` |
| ETA inference | Every inbound candidate (see [Shared definitions](#shared-definitions)) for each target airport, using the `eta@champion` model | `ml.eta_predictions` |

ETAs exist only for flights that already have a `flight_id`, so a new flight gets its first ETA after the next `flights_sessionizer` run (≤ 5 min).

- **Startup:** `ops.stream_state` is seeded with `-infinity`, so a fresh worker starts with every live snapshot. It also re-checks for new snapshots every 60 s, in case a notification was missed.
- **Squawk:** the episode is looked up in the aircraft's last 12 h. An episode reaching back to the edge of that window is skipped, since its event was already written.
- **Go-around:** the climbing observation is the current snapshot's. The descending one is the latest of the aircraft's previous 3 observations (within 30 min) with `vertical_rate_ms < −2`. Every observation from the descending one to the climbing one is within 15 km of the same target airport, below 1,000 m above it, and not `on_ground`, and none between them climbs at more than +2 m/s. So a climb that lasts several snapshots gives one event. The height uses the shared definition, with the airport's latest METAR when `core.metar` has one.
- **Titles:** `Squawk 7700 emergency (DLH4AB)`, `Squawk 7600 radio failure (…)`, `Squawk 7500 unlawful interference (…)`, `Go-around at LOWW (AUA478)`. The icao24 stands in when the callsign is unknown.

## P4 · Orchestrated jobs

Every job takes an explicit `[window_start, window_end)`, writes one `ops.job_runs` row, and is idempotent for that window. Scheduled runs derive the window from the schedule tick as listed.

| Job | Schedule (UTC) | Window | Reads | Writes |
|---|---|---|---|---|
| `flights_sessionizer` | every 5 min | last 30 min + all `active` flights | `raw.state_vectors`, `core.metar`, `ref.airports` | `core.flights` |
| `destination_inference` | every 5 min | `active` flights | `core.flights`, `ref.callsign_routes` | `ml.dest_predictions` |
| `metar_fetch` | every 30 min at :05, :35 | last 3 h of reports | aviationweather.gov | `core.metar` |
| `anomaly_scoring` | every 15 min at +2 min | the bucket that just closed | `agg.traffic_h3_15m`, `agg.coverage_15m`, `agg.baseline_h3_how` | `ml.anomalies`, `core.events` |
| `agg_backfill_refresh` | hourly at :10 | batches received since the last successful run; refreshes the days they touch | `ops.ingest_batches` | `agg.traffic_h3_15m` |
| `baseline_recompute` | daily 02:00 | 28 days before today 00:00 | `agg.traffic_h3_15m`, `agg.coverage_15m` | `agg.baseline_h3_how` |
| `flight_labels_merge` | daily 08:00 | yesterday | `raw.opensky_flights`, `core.flights` | `core.flights` |
| `routes_refresh` | daily 08:30 | 28 days before today 00:00 | `raw.opensky_flights`, Zenodo Parquet | `ref.callsign_routes` |
| `llm_briefing` | every 30 min at :01, :31 | the 30 min that just ended | facts queries ([07](07-llm.md)) | `llm.briefings` |
| `collector_gap_check` | every 5 min | last 2 h | `ops.ingest_batches` | `core.events` |
| `carbon_readings_record` | every 5 min | the 5 min ending at the tick | carbon-signal ([05](05-api-contract.md#carbon-signal-cluster-internal)) | `ops.carbon_readings` |
| `dq_checks` | hourly at :20 | last hour | `raw`, `ops` | `ops.dq_results`, `core.events` |
| `ref_refresh` | monthly, 1st at 01:00 | n/a (full reload) | OurAirports, OpenSky aircraft DB, OpenFlights, Natural Earth | `ref.*` except `callsign_routes` |
| `train_eta` | weekly Sun 03:00 | all labelled arrivals up to Sat 00:00 | Postgres extracts via DuckDB | MLflow, `ops.model_runs` |
| `backup` | daily 04:00 | n/a | database | Cloudflare R2 |
| `flights_rebuild`, `events_rebuild` | manual only | given window | `raw.state_vectors` | `core.flights`, `core.events` |
| `metar_backfill` | manual only | given window | Iowa Environmental Mesonet | `core.metar` |

### `flights_sessionizer`

- Points are processed in `(icao24, snapshot_time)` order. A point extends the aircraft's `active` flight unless a boundary occurs; otherwise a new flight opens with a new UUIDv7 `flight_id`.
- **Boundaries:** a gap > 20 min between consecutive points; `on_ground` → airborne after at least one `on_ground` point; the callsign changes from one non-NULL value to a different non-NULL value (NULL ↔ value never splits).
- **Status:** `active` while open. When a boundary closes it or its `last_seen` is > 20 min before the watermark: `completed` if an `on_ground` point was seen at the end, otherwise `lost`.
- **Finalising:** a closed flight with `last_seen` before the watermark gets `finalized = true` and is never changed by scheduled runs. Late points older than a finalized flight's `last_seen` are not attached; `flights_rebuild` picks them up.
- **Observed arrival** at a target airport A (sets `arr_icao = A`, `arr_source = 'observed'`, `arrived_at`, `arrival_method`, `height_method`):
  - `on_ground`: the first `on_ground` point within 5 km of A; `arrived_at` = its `time_position`.
  - `last_airborne`: the flight is `lost`, and its last airborne point is within 5 km of A with height above A < 300 m; `arrived_at` = that point's `time_position`.
- **Observed departure:** the first airborne point after an `on_ground` point within 5 km of a target airport sets `dep_icao`, `dep_source = 'observed'`.

### `flight_labels_merge`

For each finalized `core.flights` row of the window, find the `raw.opensky_flights` row with the same `icao24` whose `first_seen` is within 30 min of the flight's `first_seen`. Copy `est_dep_icao` and `est_arr_icao` into `dep_icao` / `arr_icao` with source `opensky`, never overwriting an `observed` value.

### `anomaly_scoring`

1. `CALL refresh_continuous_aggregate('agg.traffic_h3_15m', bucket_start, bucket_end)` for the bucket that just closed, then read it.
2. Skip the bucket when `n_global_snapshots < 5`.
3. Score every cell with the active baseline ([06](06-ml.md#1--unusual-traffic-anomaly-detection)). A cell is **flagged** when `|z| ≥ 3` and `max(observed, expected) ≥ 2`. Store flagged cells in `ml.anomalies` with `persistent = true` when the same cell was flagged in the same direction in the previous bucket.
4. **Clusters:** persistent cells of the same direction that are H3 neighbours (`grid_disk` k = 1) form one cluster. Its **anchor** is the cell with the largest `|z|`.
5. **Events** (only for clusters whose anchor centre lies in the Europe box lat 34–72, lon −25–45):
   - `anomaly_start` for a cluster none of whose cells was persistent in the previous bucket.
   - `anomaly_end` for each previous-bucket cluster none of whose cells is persistent now; the key uses the previous anchor and the current bucket.
   - Title example: "Unusually busy near Munich (EDDM), +3.8σ". `low` events append "(may be a receiver coverage gap)".

`anomaly_scoring` never runs for buckets that arrive through catch-up; history is not re-scored.

### `agg_backfill_refresh`

Find successful `states_global` batches received in the window whose `snapshot_time` is more than 2 h before `received_at`. If there are any, call `refresh_continuous_aggregate` for whole UTC days from the earliest to the latest such `snapshot_time` (ending no later than the window end).

**Window ([D11](11-tasks.md#decided-while-building)):** a scheduled run covers `received_at` from the end of the last successful run to the tick, so a failed run never leaves late data unmaterialised. The first run looks back 65 min, and the look-back is capped at 7 days. A manual run can pass both ends.

### `collector_gap_check`

A gap is a run of ≥ 4 consecutive slots (`requested_at` on the collector's 90 s grid) without a successful `states_global` batch. Insert one `collector_gap` event per gap at its first missed slot.

- Checks every collector with `disabled_at IS NULL`.
- Scheduled window: the 2 h ending 5 min before the tick, since a slot's upload can take a minute.
- A gap that began before the window keeps its real start (the last success before the window is looked up), so every run produces the same dedupe key.
- Misses before a collector's first success are not a gap; it has not started yet.
- The event says the VM has no data, so it also fires when the collector works but cannot upload.

### `carbon_readings_record`

Stores the simulated grid's carbon intensity for the carbon-aware behaviour ([ADR-0006](adr/0006-carbon-aware-operations.md)).

- Asks carbon-signal for the intensity at the window end (`GET /v1/intensity?at=`) and inserts one `ops.carbon_readings` row for that tick.
- A replayed window keeps its first reading (`ON CONFLICT DO NOTHING`): it records what the system saw then, including a demo override that may have ended since.
- If carbon-signal is unreachable the run fails and the tick has no reading; the next tick is independent.

### `backup`

1. `pg_dump -Fc airspace` excluding the chunk data of `raw.state_vectors`, `raw.opensky_flights` and every continuous aggregate's materialisation hypertable (`agg.traffic_h3_15m`; [D13](11-tasks.md#decided-while-building)): one `--exclude-table-data=_timescaledb_internal._hyper_<id>_*` pattern per hypertable, built from its chunk prefix in TimescaleDB's catalog. The pattern also covers the `<chunk>_compressed` tables, which TimescaleDB 2.30 no longer lists in its catalog. Everything else is dumped, including the aggregates' definitions.
2. `pg_dump -Fc dagster` and `pg_dump -Fc mlflow`.
3. `rclone copy` the three dumps (and, once MLflow exists, the `mlflow-artifacts` volume) to R2 `airspace-backup/YYYY-MM-DD/`. Keep the 14 newest days.
4. **R2 cap ([D7](11-tasks.md#decided-while-building)):** if backups plus `airspace-archive` exceed 8 GB, delete the oldest archive files until they fit. Backups are never deleted for the cap.

The job runs in the dagster-code container as the read-only `backup` role ([D8](11-tasks.md#decided-while-building)), with the PostgreSQL 16 client and rclone in the image. The rclone remote `r2` comes from `RCLONE_CONFIG_R2_*` variables set in `infra/compose.yml`. CI runs it against a local directory and restores the dump into a new database (`infra/test-db.sh`).

**Restore:** create the databases, `SELECT timescaledb_pre_restore();`, `pg_restore`, `SELECT timescaledb_post_restore();`, then replay the collector's R2 archives with `collector.replay` ([below](#idempotency-and-replays)). Once the raw data is back, rebuild the aggregate over the replayed range with `CALL refresh_continuous_aggregate('agg.traffic_h3_15m', <start>, <end>)`; aggregate history older than the archives is lost (D13).

## Catch-up after an outage or the M0 backlog

1. The uploader drains `pending/` oldest-first. Ingest stores the batches; none of them notify (they are not live).
2. `agg_backfill_refresh` materialises the affected days within the hour.
3. The next daily `baseline_recompute` includes them.
4. The stream-worker, the map and the event feed ignore them.

## Idempotency and replays

- **Batches:** `batch_id` makes uploads idempotent; rows use `ON CONFLICT DO NOTHING`.
- **From archives:** `python -m collector.replay --from <parquet files>` re-POSTs batches with their original `batch_id`. It only adds data for batches the database does not know (after a restore). Data older than the 90-day retention is analysed from Parquet with DuckDB, not replayed.
- **Flights:** `flights_rebuild --start --end` deletes, in one transaction, every flight whose `[first_seen, last_seen]` overlaps the window (cascading to its predictions; events keep their row with `flight_id = NULL`), then re-sessionizes the raw points from the earliest deleted `first_seen` to the latest deleted `last_seen`. Predictions are not regenerated.
- **Events:** `events_rebuild --start --end` re-runs squawk and go-around detection over the window's snapshots; duplicate keys are ignored.
- **Everything else** upserts on its primary key.

## Data-quality checks

| Check | Rule (over the last hour unless stated) | Status |
|---|---|---|
| `slot_coverage` | Share of the 40 slots with a successful `states_global` batch | warn < 95%, fail < 80% |
| `snapshot_gap` | Largest gap between consecutive successful global snapshots | warn > 120 s, fail > 300 s |
| `ingest_lag` | p95 `late_seconds` of live batches | warn > 30 s |
| `null_position_rate` | Share of state vectors without lat/lon | warn > 10% |
| `aircraft_count_range` | Latest snapshot has 3,000–20,000 states | fail outside |
| `physical_bounds` | Rows with altitude ∉ [−500, 20,000] m or velocity > 400 m/s | warn > 0.1% |
| `staleness` | Median `snapshot_time − last_contact` | warn > 30 s |
| `credits_remaining` | Projected quota left at the next reset at the current rate. The reset time is taken from the data: the last time `credits_remaining` jumped back up, plus 24 h (about 16:10 UTC, [02](02-data-sources.md)) | warn < 0 |
| `flight_lists_loaded` | Daily at 19:00: yesterday has 12 successful `flights_all` windows | fail otherwise |

Grafana shows them as a traffic-light table. Every `fail` also inserts a `dq_fail` event.

The **weekly collection target** ([00](00-overview.md#success-criteria)) is computed the same way as `slot_coverage`, over 7 days.

## Stretch: holding detection

Built only if the roadmap promotes it. Within 60 km of a target airport, a flight is holding when its last 15 min of positions form a polyline that crosses itself. Heading-change sums are not used: at 90 s sampling a 270° turn aliases to −90°.
