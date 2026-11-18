# 11 · Tasks and status

The working task list for the whole application, by milestone ([10](10-roadmap.md)). The specs live in the other docs; this file only says what exists and what is left. Update a task's status in the same PR as the work.

Status: ✅ done · 🟡 in progress · ⬜ to do · ⛔ blocked (the note says on what).
Track: **A** = data platform, **B** = product & ML ([work split](10-roadmap.md#work-split)). Track A is owned by Dániel, Track B by Alek.

*Last updated: 2026-11-18.*

## What exists now

| Area | State |
|---|---|
| Docs | Grounding docs 00–10 and ADRs 0001–0004 on `main` |
| Python workspace | uv workspace at the repo root (Python 3.12): `collector`, `libs/airspace_common`. ruff, mypy (on `libs/`), pytest. `.gitignore`, `.env.example` |
| `libs/airspace_common` | `settings.py` (collector settings), `timefmt.py` (`iso_z`), `log.py` (structlog JSON) |
| Collector v0 | State-vector loop on the 90 s grid, OAuth2 token handling, atomic spool writes, failure handling (retry, 429 back-off, failed envelopes), daily flight-list task with restart-safe progress, single-instance lock, `status` command. 38 tests |
| Collection | **pi-daniel collecting 24/7 since 2026-11-07** on the Raspberry Pi (Debian 13 arm64, 4 GB RAM, 64 GB microSD) in Docker (`collector/compose.yml`). pc-daniel collected 2026-10-29 to 11-07, off overnight; its task `airspace-collector` is stopped and must stay disabled (D4) |
| Server | Oracle A1 VM `airspace-vm` (Frankfurt, 2 OCPU, 12 GB, 200 GB) with Docker and Tailscale, created 2026-10-30. No inbound ports open to the internet. Runs the database and ingest-api from a git checkout of `main`, deployed with `infra/deploy.sh` |
| Pipeline | pc-daniel uploads to ingest-api on the VM over Tailscale; batches land in TimescaleDB. On 2026-11-03: 2,780 snapshots, 27.5M state vectors, 314k flight-list rows, nothing rejected; database 6.5 GB, uncompressed |
| Orchestrator | Dagster on the VM (tailnet `:3000`): `backup` daily 04:00 UTC to R2, `collector_gap_check` every 5 min |
| Dashboards | Grafana "Airspace ops" on the tailnet (`airspace-vm:3001`) |
| Not started | stream worker, web app, ML, LLM |
| public-api | `services/api` serves all of M2.1 as `app_reader`: `/live/snapshot`, `/stats`, `/aircraft/{icao24}`, `/aircraft/{icao24}/track`, `/events`, `/live/stream` (SSE), `/health` |

## Open questions found while building

| # | Question | Why it matters |
|---|---|---|
| Q1 | The remaining decisions flagged in the 2026-10-29 decision review: chat as free text-to-SQL vs fixed query tools; single VM vs k3s or managed services; Oracle vs Contabo; Dagster vs cron; TimescaleDB as the only store | Each is cheaper to change now than after M1 |
| Q2 | Zenodo record for the route fallback. DOI 10.5281/zenodo.3737101 (2019–2022, has `icao24`) has a non-commercial licence; 10.5281/zenodo.5815448 (2019–2021, anonymised aircraft) is CC BY 4.0. Routes only need `callsign`, `origin` and `destination` | Decide before M3.5; the README and [02](02-data-sources.md) cite the record in use |
| Q3 | `flights_sessionizer` reads the last 30 min, so a backlog drained after an outage is never turned into flights without a manual `flights_rebuild` | With one home collector, outages will happen; those arrivals are lost as ETA labels |
| Q5 | CARTO basemap: raster tiles need an API key. Add the key, a tile budget and the Pages preview origins to [08](08-frontend.md) | Needed for M2 |
| Q6 | A stream-worker outage over 10 min loses squawk and go-around events until someone runs `events_rebuild` | Add bounded catch-up on startup, or schedule the rebuild |
| Q8 | CORS preview origins need a regex or allow-list; `Access-Control-Allow-Origin` has no wildcard subdomains | [05](05-api-contract.md) reads as a literal `*.pages.dev` |
| Q9 | What happens to `ml.anomalies` when late data changes a bucket: re-score or mark stale | The heatmap can disagree with the aggregate |
| Q10 | A negative-result path for ETA: report MAE vs B0 and B1 and keep the model card even if B1 is not beaten | B1 is a strong baseline and the success criterion may not be met |
| Q11 | Validate H3 resolution 4 against real traffic, or test 5 or 6 for Central Europe | A 1,770 km² cell may only show overflight patterns |
| Q12 | Golden-set questions that depend on `now()` need a frozen fixture clock; `llm.v_live_aircraft` should respect the 10-minute live window or label stale answers | Flaky eval; stale answers presented as live |
| Q13 | Dead reckoning with `pos_age_s = null`, and whether `H3HexagonLayer` can draw a dashed outline | Small but visible map bugs |
| Q14 | OpenFlights is ODbL 1.0: check whether share-alike applies to our airline table, or use a CC0 list | Attribution alone may not be enough |
| Q15 | A reference device and connection for the "< 3 s, 60 fps" criterion in [00](00-overview.md#success-criteria) | Otherwise it can't be tested |
| Q16 | Raw compression is 2.9× (69 B/row) against the ~10× estimated; sorted Parquet reached 17 B/row. Check the `segmentby`/`orderby` settings and the index on the compressed chunks | At 24/7 collection 90 days is ~60–65 GB instead of ~30 GB; it still fits the 200 GB disk |

Q5–Q15 carry over the findings still open from the 2026-10-30 documentation review.

## Decided while building

| # | Decision | Why |
|---|---|---|
| D1 | No off-PC copy of collected data before M1. Compaction and the R2 archive upload run on uploaded (`sent/`) files only, and move to M1 | Building an early archive path for ~2 weeks of risk is not worth it. Accepted risk: until the uploader runs, `spool/` is the only copy. Never run `git clean -x` in the repo and never move or delete `spool/` (decided 2026-10-29) |
| D2 | OurAirports airports and runways are seeded in M1 (`db/seeds/ourairports.py`), not first loaded in M3 | Go-around detection (M2) needs target-airport elevations. One source of truth instead of hard-coded constants (decided 2026-10-29) |
| D3 | While the project is private, the VM is reachable over Tailscale only and the collector uploads over the tailnet. Cloudflare, the domain, Caddy and port 443 wait until before a public launch | Nothing is public yet, so nothing needs to be open to the internet or paid for. Supersedes the `ingest.<domain>` path until then (decided 2026-10-30) |
| D4 | One collector; the map refreshes every 90 s | One collector keeps collection simple, 90 s fits the API quota, and the map moves smoothly between snapshots (decided 2026-10-30) |
| D5 | A Raspberry Pi becomes the collector and runs 24/7. pc-daniel collected until then and was switched off overnight | A device that stays on removes the overnight gaps. Gaps before the switch are accepted, not treated as faults (decided 2026-10-31; switched 2026-11-07) |
| D6 | The collector keeps 30 days of Parquet archives locally (`ARCHIVE_RETENTION_DAYS=30`), down from 90. The VM database is the main store and R2 the off-site copy (capped by D7) | About 6 GB on the Pi's 64 GB SD card instead of 15–20 GB (decided 2026-11-07) |
| D7 | R2 stays inside its 10 GB free tier: backups plus archives are capped at 8 GB. The daily `backup` job deletes the oldest `airspace-archive` files when the total passes the cap; backups (14 days) are never deleted for it | Enabling R2 needs a card, and nothing may be billed. At ~0.2 GB of Parquet a day the archive holds the last ~5 weeks, more than the Pi's 30 days; older raw data lives only in the database (90 days) (decided 2026-11-08) |
| D8 | `pg_dump` runs from the dagster-code container as a read-only `backup` role (`pg_read_all_data`), not inside the database container | Running it in the database container would need the Docker socket in Dagster, which is root on the VM (decided 2026-11-08) |
| D9 | The collector exits after 10 consecutive slots with no response from OpenSky, so Docker restarts it | A Pi reboot on 2026-11-13 left the container with an empty `resolv.conf`; it collected nothing for 2.7 days without crashing, and a restart fixed it (decided 2026-11-16) |
| D10 | The OurAirports seed loads airports with an ICAO code and an elevation (10,398 of 86,371), and open runways with an `le_ident` (11,211); a repeated `(airport, le_ident)` keeps the longest runway. Resolves Q4 | 335 ICAO airports have no elevation and a guessed 0 would give wrong heights; 16 runways have no identifier and 2 identifiers repeat. None of them is at a target airport (decided 2026-11-17) |
| D11 | `agg_backfill_refresh` scans batches received since the end of its last successful run (first run: 65 min; at most 7 days), not a fixed 65 min. Resolves Q7 | A single failed hourly run would otherwise leave late data unmaterialised for good (decided 2026-11-17) |
| D12 | Grafana is reachable on the tailnet only (`airspace-vm:3001`, admin login) until the public launch; externally shared dashboards wait for the domain and Cloudflare (M1.2) | Same reason as D3: nothing is public yet (decided 2026-11-17) |

## M0 · Foundations (weeks 0–1)

| # | Task | Track | Status | Notes |
|---|---|---|---|---|
| M0.1 | Grounding docs and ADRs | both | ✅ | |
| M0.2 | OpenSky account and API client | A | ✅ | Token verified 2026-10-29 |
| M0.5 | Decide track owners | both | ✅ | 2026-11-03: Track A Dániel, Track B Alek |
| M0.6 | Decide O5 (name and domain); register the domain on Cloudflare | both | ⬜ | No longer blocks M1 (D3); needed before a public launch |
| M0.7 | Python workspace, lint, type check, tests | A | ✅ | |
| M0.8 | Collector v0 (loop, spool, failures, flight lists, lock, status) | A | ✅ | `collector/` |
| M0.9 | Run the collector on pc-daniel as a scheduled task | A | ✅ | Task `airspace-collector` (S4U, at startup) since 2026-10-29. Switched off overnight until the Pi takes over (D5) |
| M0.13 | 48 h check: a spool file every 90 s; yesterday's flight lists arrive | A | ✅ | Checked 2026-11-17 over the last 24–48 h: 875 of 931 slots succeeded (94%; the failures are Pi Wi-Fi drops) and all 24 flight-list windows arrived |
| M0.14 | Write measured rows/day and file sizes into [01 Sizing](01-architecture.md#sizing) | A | ✅ | Rows/day, bytes/row, compressed size (VM) and Parquet size (Pi, 2026-11-17: ~185 MB/day, 21 B/row) written into 01 |
| M0.15 | Request the Oracle A1 VM; order the Contabo fallback if none by the end of week 1 | A | ✅ | VM created 2026-10-30; no fallback needed. Cost Analysis shows 0 HUF for 2026-10-30 to 11-05 |
| M0.16 | Teammate review of the docs rewrite (pushed to `main` without a PR) | B | ⬜ | Commit `5ad79a1` |
| M0.17 | Product owner decisions (core vs stretch, hosting, dropped items, data limits) | both | ⬜ | |
| M0.18 | Verify the flight-list quota cost and the Zenodo DOI ([02](02-data-sources.md)) | A | ✅ | Quota measured 2026-10-29. DOI checked 2026-10-31: it is not CC BY (Q2) |
| M0.19 | Collector Dockerfile (amd64 + arm64) | A | ✅ | `collector/Dockerfile` and `collector/compose.yml` (host networking, spool bind mount, small Docker logs). Built on the Pi; not yet built in CI (M1.14) |
| M0.20 | Move the collector to the Raspberry Pi: 64-bit OS, Tailscale, Docker, its own `add-collector` key | A | ✅ | Switched 2026-11-07 as `pi-daniel`, with the PC's flight-list progress copied over. pc-daniel's spool was fully uploaded; keep its `spool/sent` until backups exist (D1). Since 2026-11-16 the Pi's `~/airspace` is a git checkout of `main` (converted in place; `spool/` and `.env` untouched) |

## M1 · Platform (weeks 1–2)

| # | Task | Track | Status | Notes |
|---|---|---|---|---|
| M1.1 | VM: Ubuntu 24.04, Docker, Tailscale; OCI security list (22 closed; 443 from Cloudflare only added with M1.2) | A | ✅ | Done 2026-10-30. Public port 22 closed and checked; login over Tailscale works; VM key expiry disabled |
| M1.2 | Cloudflare DNS (`api`, `ingest`, `grafana` proxied, Full strict), Origin CA certificate, Caddy | A | ⬜ | Moved to before a public launch (D3). Needs M0.6 |
| M1.3 | `infra/compose.yml` and `compose.dev.yml`; pinned `timescaledb-ha` image (TimescaleDB ≥ 2.19) | A | ✅ | `pg16.15-ts2.30.2`. Database running on the VM since 2026-10-30; files copied by hand until M1.15 |
| M1.4 | Migrations: schemas, roles, `ops`, `raw` (no compression policy), `ref`, `core`, `agg`, `ml`, `llm` ([03](03-data-model.md)) | A | ✅ | `agg.traffic_h3_15m` and `agg.coverage_15m` come with M1.10; `llm.v_*` with the chat. Open for M2: `stream_worker` has no INSERT on `ops.stream_state`, so its first row needs a decision |
| M1.5 | CI migration test, including the compressed-chunk `ON CONFLICT` test (timescaledb#7672) | A | 🟡 | `infra/test-db.sh` and `db/tests/test_schema.sql` pass on the VM; Wired into `ci.yml` (M1.14) |
| M1.6 | ingest-api `POST /ingest/v1/batches` ([05](05-api-contract.md#post-ingestv1batches)) | A | ✅ | Running on the VM since 2026-10-30, built there by hand until M1.15. `infra/test-db.sh` covers it end to end |
| M1.7 | Admin CLI `add-collector` (argon2id key hash) | A | ✅ | Run through the `ingest-admin` compose service |
| M1.8 | Collector uploader (oldest-first, back-off, 401/413/422 handling); then `UPLOAD_ENABLED=true` | A | ✅ | Enabled on pc-daniel 2026-10-30 |
| M1.9 | Drain the M0 backlog | A | ✅ | Drained 2026-10-30: 736 snapshots, 8.75M state vectors, 119,723 flights, nothing rejected. About 230 B/row before compression, so M1.11 matters next |
| M1.10 | `agg.traffic_h3_15m`, `agg.coverage_15m`, `agg_backfill_refresh` | A | ✅ | 2026-11-17. The aggregate is created as `jobs` (which must own it to refresh it). History since 2026-10-29 was materialised once by hand; the policy keeps the last 2 h current and the hourly job handles late batches ([D11](#decided-while-building)) |
| M1.11 | Compression-policy migration, merged after the drain | A | ✅ | Applied on the VM 2026-11-05 (job 1005, every 12 h). First run compressed 5 days from 6.0 GB to 2.1 GB (2.9×, 69 B/row), lower than the ~10× estimated (Q16) |
| M1.12 | Dagster webserver, daemon and code location (tailnet only) | A | ✅ | 2026-11-08: one image (`services/orchestrator`) runs all three; storage in the `dagster` database; webserver on `127.0.0.1:3000`, shared to the tailnet with `tailscale serve`. CI's migration test also checks that the webserver loads the `airspace` code location. No jobs yet; `backup` (M1.16) is the first |
| M1.13 | Grafana provisioning; ops dashboards (rows/min, slot coverage, gaps), externally shared | A | ✅ | 2026-11-17: Grafana 12.4.3 with the datasource (`grafana_reader`) and the "Airspace ops" dashboard provisioned from `infra/grafana`; CI runs every panel query as `grafana_reader`. Tailnet only ([D12](#decided-while-building)); external sharing comes with M1.2 |
| M1.14 | `ci.yml`: ruff, mypy, pytest, ESLint, tsc, Vitest, migration test, multi-arch build | A | ✅ | Green since 2026-11-08 in the `airspace-monitor` organization (the repo moved there because Actions would not start on the previous owner's account). Python checks, `infra/test-db.sh`, amd64 + arm64 builds of ingest and collector. JS checks join with `web/` |
| M1.15 | `deploy.yml` and `infra/deploy.sh` (Tailscale, pull → migrate → up), GHCR | A | ✅ | Live since 2026-11-08: every merge to `main` runs CI, then deploys to the VM over Tailscale (first automatic deploy: PR #12). Images build on the VM; GHCR deferred |
| M1.16 | Daily `backup` job to R2; restore drill | A | ✅ | Live 2026-11-16 (Dagster, daily 04:00 UTC). First backup 0.78 MB, since raw chunk data is left out. Restore drill from R2 into a scratch database matched the live `ops` tables. CI repeats the drill on every PR. Raw data is not in the backups: until M1.20 its only off-VM copies are the collectors' `spool/sent` |
| M1.17 | Local dev command with the fixture database | A | ⬜ | |
| M1.18 | OurAirports seed loader `db/seeds/ourairports.py` (`ref.airports`, `ref.runways`) | A | ✅ | 2026-11-17: 10,398 airports and 11,211 runways ([D10](#decided-while-building)); LOWW, LZIB and LHBP flagged as targets. `infra/test-db.sh` loads a fixture twice |
| M1.19 | Spool compaction to Parquet at 00:30 UTC (uploaded files only) | A | ✅ | 2026-11-17. Dry run on the Pi with a copy of 2026-11-12: 8,633,048 state rows and 18,392 flight rows, exactly the database's counts for those batches; 3 min, 363 MB RAM. Local retention and the R2 upload are M1.20 |
| M1.20 | R2 bucket `airspace-archive`, `rclone copy` at 01:00 UTC, local retention (`ARCHIVE_RETENTION_DAYS=30`, `RCLONE_REMOTE`) | A | ✅ | Live 2026-11-18: the upload runs right after the 00:30 compaction with the Pi's own token (only `airspace-archive`). First upload: 17 files, 1.06 GB in 30 s, now that the Pi is on Ethernet. Local archives older than 30 days are deleted only once R2 holds them at the same size |
| M1.21 | Remove the leftover collector offset: forward migration dropping `ops.collectors.offset_seconds`, `OFFSET_SECONDS` in settings and `.env.example`, `--offset` in the admin CLI | A | ✅ | 2026-11-17, in two steps so each migration worked with the running code: the code stopped using it (column default 0), then the column was dropped and `ops.v_collectors` recreated. A leftover `OFFSET_SECONDS` in a `.env` is ignored |

## M2 · Live map (weeks 2–4)

| # | Task | Track | Status | Notes |
|---|---|---|---|---|
| M2.1 | public-api: `/live/snapshot`, `/live/stream` (SSE), `/aircraft/{icao24}`, `/aircraft/{icao24}/track`, `/events`, `/stats`, `/health` | B | 🟡 | `services/api` serves all seven endpoints (129 tests, checked against the VM database). Left: a Dockerfile and a compose entry so it runs on the VM (M1.15) |
| M2.2 | stream-worker: squawk and go-around events, `ops.stream_state` | A | ⬜ | Go-arounds use `ref.airports` from M1.18 |
| M2.3 | `metar_fetch` job | A | ⬜ | |
| M2.4 | Web app shell: layout, header stats, attribution footer, bottom sheet under 900 px | B | ⬜ | |
| M2.5 | Map: aircraft layer, altitude colours, smooth motion, aircraft card, selected trail | B | ⬜ | |
| M2.6 | Events panel with cursor paging and map fly-to | B | ⬜ | |
| M2.7 | Cloudflare Pages project with PR previews | B | ⬜ | |
| M2.8 | Cloudflare rate-limit rule, firewall, CORS | A | ⬜ | |
| M2.9 | Every item in [01 Networking and security](01-architecture.md#networking-and-security) checked before the URL is shared | both | ⬜ | |

## M3 · Curated data (weeks 3–5)

| # | Task | Track | Status | Notes |
|---|---|---|---|---|
| M3.1 | `ref_refresh`: airports, runways, aircraft, airlines, countries, H3 → country | A | ⬜ | Takes over the M1.18 seed for airports and runways |
| M3.3 | `flights_sessionizer` (watermark, boundaries, observed arrivals and departures) | A | ⬜ | |
| M3.4 | `flight_labels_merge` | A | ⬜ | |
| M3.5 | `routes_refresh` (OpenSky flight lists plus Zenodo fallback) | A | ⬜ | |
| M3.6 | `metar_backfill` from Iowa Environmental Mesonet | A | ⬜ | |
| M3.7 | `dq_checks` and the Grafana traffic-light table | A | ⬜ | |
| M3.8 | `collector_gap_check` | A | ✅ | Pulled forward from M3 on 2026-11-16, after the Pi's 2.7-day outage went unnoticed. Dagster, every 5 min; writes `ops.job_runs`. Events are only in the database until a dashboard or the frontend shows them. `pc-daniel` was disabled (`disabled_at`) so it is not checked |
| M3.9 | `flights_rebuild`, `events_rebuild`, `collector.replay` | A | ⬜ | |

## M4 · ML (weeks 4–6)

| # | Task | Track | Status | Notes |
|---|---|---|---|---|
| M4.1 | `baseline_recompute` | A | ⬜ | Needs ≥ 3 weeks of data for full baselines |
| M4.2 | `anomaly_scoring`: scoring, persistence, clusters, events | B | ⬜ | |
| M4.3 | `/anomalies` endpoint and heatmap layer with legend | B | ⬜ | |
| M4.4 | Anomaly evaluation (synthetic injection, events/day) and model card | B | ⬜ | |
| M4.5 | MLflow on the VM (tailnet only); `ops.model_runs`; public Grafana Models dashboard | B | ⬜ | |
| M4.6 | ETA training data, features, baselines B0 and B1 | B | ⬜ | |
| M4.7 | ETA LightGBM quantile models; weekly `train_eta`; promotion rule | B | ⬜ | |
| M4.8 | ETA inference in the stream-worker; `/arrivals`; arrivals board | B | ⬜ | |
| M4.9 | `destination_inference` (route lookup); top-3 in the aircraft card | B | ⬜ | |
| M4.10 | Destination accuracy vs the nearest-airport baseline; model cards | B | ⬜ | |

## M5 · LLM (weeks 5–7)

| # | Task | Track | Status | Notes |
|---|---|---|---|---|
| M5.1 | `services/llm` client, versioned prompts, Anthropic spend limit $40/month | B | ⬜ | |
| M5.2 | Briefing facts queries, `llm_briefing` job, number check, `/briefing/latest`, Briefing panel | B | ⬜ | |
| M5.3 | `llm.v_*` views, `db/llm_views.md`, `llm_readonly` role | B | ⬜ | |
| M5.4 | `POST /chat` with guardrails and limits; Ask panel | B | ⬜ | |
| M5.5 | Golden set (30+), fixture database, `llm-eval.yml` (≥ 80%) | B | ⬜ | |

## M6 · Portfolio polish (weeks 7–8)

| # | Task | Track | Status | Notes |
|---|---|---|---|---|
| M6.1 | README architecture diagram and demo video | both | ⬜ | |
| M6.2 | Final model cards | B | ⬜ | |
| M6.3 | Final report | both | ⬜ | |

## Stretch

Not started. Only after every M0–M5 "done when" is met, in the order of [10 Stretch](10-roadmap.md#stretch).
