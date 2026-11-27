# 11 · Tasks and status

The working task list for the whole application, by milestone ([10](10-roadmap.md)). The specs live in the other docs; this file only says what exists and what is left. Update a task's status in the same PR as the work.

Status: ✅ done · 🟡 in progress · ⬜ to do · ⛔ blocked (the note says on what).
Track: **A** = data platform, **B** = product & ML ([work split](10-roadmap.md#work-split)). Track A is owned by Dániel, Track B by Alek.

*Last updated: 2026-11-27.*

## What exists now

| Area | State |
|---|---|
| Docs | Grounding docs 00–10 and ADRs 0001–0006 on `main` |
| Python workspace | uv workspace at the repo root (Python 3.12): `collector`, `libs/airspace_common`. ruff, mypy (on `libs/`), pytest. `.gitignore`, `.env.example` |
| `libs/airspace_common` | `settings.py` (collector settings), `timefmt.py` (`iso_z`), `log.py` (structlog JSON) |
| Collector v0 | State-vector loop on the 90 s grid, OAuth2 token handling, atomic spool writes, failure handling (retry, 429 back-off, failed envelopes), daily flight-list task with restart-safe progress, single-instance lock, `status` command. 38 tests |
| Collection | **pi-daniel collecting 24/7 since 2026-11-07** on the Raspberry Pi (Debian 13 arm64, 4 GB RAM, 64 GB microSD) in Docker (`collector/compose.yml`). pc-daniel collected 2026-10-29 to 11-07, off overnight; its task `airspace-collector` is stopped and must stay disabled (D4) |
| Server | Oracle A1 VM `airspace-vm` (Frankfurt, 2 OCPU, 12 GB, 200 GB) with Docker and Tailscale, created 2026-10-30. No inbound ports open to the internet. Runs the database, ingest-api, public-api, stream-worker, Dagster and Grafana as pods on single-node k3s since 2026-11-23 ([ADR-0005](adr/0005-single-node-k3s.md)), from a git checkout of `main`, deployed with `infra/deploy.sh` |
| Pipeline | pc-daniel uploads to ingest-api on the VM over Tailscale; batches land in TimescaleDB. On 2026-11-03: 2,780 snapshots, 27.5M state vectors, 314k flight-list rows, nothing rejected; database 6.5 GB, uncompressed |
| Orchestrator | Dagster on the VM (tailnet `:3000`): `backup` daily 04:00 UTC to R2, `collector_gap_check` every 5 min |
| Dashboards | Grafana "Airspace ops" on the tailnet (`airspace-vm:3001`) |
| Stream worker | `services/stream` in the compose stack: squawk (Europe only, [D14](#decided-while-building)) and go-around events into `core.events` from every live snapshot |
| Web app | `web/` React 19 + Vite: layout, live header from `/stats`, Events feed with cursor paging and map fly-to, tabs, attribution, bottom sheet. MapLibre + deck.gl map with altitude colours, smooth motion, hover, selected trail and aircraft card; all lazy-loaded |
| Not started | ML scoring, ETA, destination, LLM |
| public-api | `services/api` serves all of M2.1 as `app_reader`: `/live/snapshot`, `/stats`, `/aircraft/{icao24}`, `/aircraft/{icao24}/track`, `/events`, `/live/stream` (SSE), `/health`. Runs in the compose stack on the VM (`127.0.0.1:8001`). CORS and an in-memory 60/10 s limiter are in the app; the Cloudflare edge rule is still an operator action |

## Open questions found while building

| # | Question | Why it matters |
|---|---|---|
| Q1 | The remaining decisions flagged in the 2026-10-29 decision review: chat as free text-to-SQL vs fixed query tools; ~~single VM vs k3s or managed services~~ (single-node k3s, [D15](#decided-while-building)); Oracle vs Contabo; Dagster vs cron; TimescaleDB as the only store | Each is cheaper to change now than after M1 |
| Q2 | ~~Zenodo record for the route fallback~~ Resolved: no Zenodo fallback ([D17](#decided-while-building)) | Closed 2026-11-25 |
| Q3 | `flights_sessionizer` reads the last 30 min, so a backlog drained after an outage is never turned into flights without a manual `flights_rebuild` | With one home collector, outages will happen; those arrivals are lost as ETA labels |
| Q5 | CARTO basemap: the key is set locally in `web/.env` (git-ignored, never committed); the Pages workflow and docs now name `VITE_CARTO_KEY`, but the secret still needs adding to the Pages/GitHub environment, and the key needs a domain restriction + tile budget | Needed for M2 |
| Q6 | A stream-worker outage over 10 min loses squawk and go-around events until someone runs `events_rebuild` | Add bounded catch-up on startup, or schedule the rebuild |
| Q8 | ~~CORS preview origins need a regex or allow-list~~ Resolved: `CORS_ALLOWED_ORIGINS` + `CORS_ALLOWED_ORIGIN_REGEX` in public-api; tests cover previews | Set the production domain in `infra/.env` |
| Q9 | What happens to `ml.anomalies` when late data changes a bucket: re-score or mark stale | The heatmap can disagree with the aggregate |
| Q10 | A negative-result path for ETA: report MAE vs B0 and B1 and keep the model card even if B1 is not beaten | B1 is a strong baseline and the success criterion may not be met |
| Q11 | Validate H3 resolution 4 against real traffic, or test 5 or 6 for Central Europe | A 1,770 km² cell may only show overflight patterns |
| Q12 | Golden-set questions that depend on `now()` need a frozen fixture clock; `llm.v_live_aircraft` should respect the 10-minute live window or label stale answers | Flaky eval; stale answers presented as live |
| Q13 | Dead reckoning with `pos_age_s = null`, and whether `H3HexagonLayer` can draw a dashed outline | Null now refuses extrapolation; H3 dashed outline remains a small visible map bug |
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
| D13 | Backups leave out continuous-aggregate data (`agg.traffic_h3_15m`) as well as raw chunk data. After a restore the aggregate is refreshed from the replayed raw data | With the aggregate's 11.5M rows the daily dump grew from 0.8 MB to 210 MB, and 14 such copies (3–4 GB, growing) would push the archives under the Pi's 30 days within the D7 cap. The aggregate is derived from raw; accepted loss: aggregate history older than the R2 archives (decided 2026-11-18) |
| D14 | Squawk events only count airborne observations with a position inside a Europe box (lat 35–72, lon −25–45), and an episode needs 3 of them before it becomes an event | Over 7 days (2026-11-15 to 22), 7500, 7600 and 7700 appeared worldwide as often as ordinary codes such as 7300 and 7400: about 30 episodes per code per day even with 3 airborne observations, and neither a code change nor a steady code told them apart. The rule as first written would have produced ~490 events a day, almost all noise. Inside Europe, 7700 stood out (15 a week, against 2–5 for the control codes). Expect ~21 events a week, the 7500 and 7600 ones still partly noise (decided 2026-11-22) |
| D15 | The server runs on single-node k3s on the existing VM, and the Pi stays a Docker edge node outside the cluster. Compose stays for local dev and CI. Carbon-aware behaviour shifts heavy jobs in time and switches eco profiles instead of moving work between nodes | The course feedback asked for cloud aspects beyond one Compose setup. Oracle's Always Free A1 allowance is now 2 OCPU / 12 GB per tenancy, all used by this VM, so a second free node is impossible; OKE could not include the Pi. Only the collector could run on the Pi, and it must not break ([ADR-0005](adr/0005-single-node-k3s.md), decided 2026-11-22) |
| D16 | A flight opens at its first airborne point; points on the ground with no open flight are only context (the one just before a takeoff sets the observed departure). Ground points after a landing still extend the arriving flight, so `completed` and `on_ground` arrivals are unchanged | Following the spec literally made every aircraft seen only on the ground (parked or taxiing) a flight: 1,594 aircraft in 6 h on the VM on 2026-11-25, ~6,000 extra rows a day beside ~24,000 real flights, which training and the aircraft card would have to filter out (decided 2026-11-25) |
| D17 | `routes_refresh` builds routes from the OpenSky flight lists only; the Zenodo fallback is dropped. Callsigns without a flight-list entry in the last 28 days get no route | By M3.5 the VM held 28 days of flight lists (since 2026-10-28, 1.26M flights, 197k callsigns with an arrival), the whole window the job reads, so the fallback would barely be used; it would add a one-off Parquet conversion, a licence question (Q2) and 2019–2022 COVID-era routes. The `zenodo` value stays allowed in the schema but is not written (decided 2026-11-25) |

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
| M1.5 | CI migration test, including the compressed-chunk `ON CONFLICT` test (timescaledb#7672) | A | ✅ | `infra/test-db.sh` and `db/tests/test_schema.sql` (with the #7672 test) run in `ci.yml` on every PR and push (M1.14) |
| M1.6 | ingest-api `POST /ingest/v1/batches` ([05](05-api-contract.md#post-ingestv1batches)) | A | ✅ | Running on the VM since 2026-10-30, built there by hand until M1.15. `infra/test-db.sh` covers it end to end |
| M1.7 | Admin CLI `add-collector` (argon2id key hash) | A | ✅ | Run through the `ingest-admin` compose service |
| M1.8 | Collector uploader (oldest-first, back-off, 401/413/422 handling); then `UPLOAD_ENABLED=true` | A | ✅ | Enabled on pc-daniel 2026-10-30 |
| M1.9 | Drain the M0 backlog | A | ✅ | Drained 2026-10-30: 736 snapshots, 8.75M state vectors, 119,723 flights, nothing rejected. About 230 B/row before compression, so M1.11 matters next |
| M1.10 | `agg.traffic_h3_15m`, `agg.coverage_15m`, `agg_backfill_refresh` | A | ✅ | 2026-11-17. The aggregate is created as `jobs` (which must own it to refresh it). History since 2026-10-29 was materialised once by hand; the policy keeps the last 2 h current and the hourly job handles late batches ([D11](#decided-while-building)) |
| M1.11 | Compression-policy migration, merged after the drain | A | ✅ | Applied on the VM 2026-11-05 (job 1005, every 12 h). First run compressed 5 days from 6.0 GB to 2.1 GB (2.9×, 69 B/row), lower than the ~10× estimated (Q16) |
| M1.12 | Dagster webserver, daemon and code location (tailnet only) | A | ✅ | 2026-11-08: one image (`services/orchestrator`) runs all three; storage in the `dagster` database; webserver on `127.0.0.1:3000`, shared to the tailnet with `tailscale serve`. CI's migration test also checks that the webserver loads the `airspace` code location. No jobs yet; `backup` (M1.16) is the first |
| M1.13 | Grafana provisioning; ops dashboards (rows/min, slot coverage, gaps), externally shared | A | ✅ | 2026-11-17: Grafana 12.4.3 with the datasource (`grafana_reader`) and the "Airspace ops" dashboard provisioned from `infra/grafana`; CI runs every panel query as `grafana_reader`. Tailnet only ([D12](#decided-while-building)); external sharing comes with M1.2 |
| M1.14 | `ci.yml`: ruff, mypy, pytest, ESLint, tsc, Vitest, migration test, multi-arch build | A | ✅ | Green since 2026-11-08 in the `airspace-monitor` organization (the repo moved there because Actions would not start on the previous owner's account). Python checks, `infra/test-db.sh`, amd64 + arm64 builds of ingest, api, collector and orchestrator. JS checks in `web/`: ESLint, tsc, Vitest and the production build |
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
| M2.1 | public-api: `/live/snapshot`, `/live/stream` (SSE), `/aircraft/{icao24}`, `/aircraft/{icao24}/track`, `/events`, `/stats`, `/health` | B | ✅ | `services/api` serves all seven endpoints as `app_reader` (130 tests). `Dockerfile` and compose service `public-api` (`127.0.0.1:8001`); built and smoke-tested on the VM 2026-11-15. `/stats` keeps TimescaleDB chunk exclusion (61 s → 23 ms at 85M rows). Left for M2.8: CORS and `tailscale serve` |
| M2.2 | stream-worker: squawk and go-around events, `ops.stream_state` | A | ✅ | 2026-11-22: `services/stream`, role `stream_worker`, LISTEN `new_snapshot` plus a 60 s re-check; progress in `ops.stream_state` (seeded with `-infinity`). Squawk events only in the Europe box after 3 airborne observations ([D14](#decided-while-building)). Go-arounds at the `ref.airports` targets; height uses METAR QNH once `metar_fetch` (M2.3) fills `core.metar`. CI runs the worker against live-timed snapshots. ETA inference joins when the `eta` model exists (M4) |
| M2.3 | `metar_fetch` job | A | ✅ | 2026-11-25: Dagster at :05 and :35, last 3 h for the `is_target` airports from aviationweather.gov into `core.metar` (SI units; visibility from the raw report). Upsert, so replays write nothing and corrections replace. CI runs it against a local fixture. The stream-worker's go-around heights switch to QNH from the first report |
| M2.4 | Web app shell: layout, header stats, attribution footer, bottom sheet under 900 px | B | ✅ | `web/` Vite 8 + React 19 + TypeScript strict: live header (`/stats`), Events feed (`/events`), tabs, attribution, bottom sheet under 900 px. Shell ~83 KB gzip JS + ~5 KB CSS; `MapPane` is a lazy chunk. ESLint/Prettier/Vitest; CI runs the web checks |
| M2.5 | Map: aircraft layer, altitude colours, smooth motion, aircraft card, selected trail | B | ✅ | MapLibre + deck.gl aircraft layer, CARTO basemap with fallback, altitude colours, hover, click card, dead-reckoning/easing/fade and the selected trail + 2 px halo. 37 web tests |
| M2.6 | Events panel with cursor paging and map fly-to | B | ✅ | `useInfiniteQuery` over `/events` cursor, infinite scroll + "Load older", clicking an event with coordinates flies the map to zoom 8. |
| M2.7 | Cloudflare Pages project with PR previews | B | 🟡 | `web/wrangler.toml`, `pages.yml`, `_headers`, env docs are in place. Actual project/deploy needs `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `VITE_API_BASE` and `VITE_CARTO_KEY`; blocked by M2.8/M1.2 to make the API publicly reachable. |
| M2.8 | Cloudflare rate-limit rule, firewall, CORS | A | 🟡 | API CORS (production origins + Pages previews) and the 60/10 s in-memory limiter are implemented and tested. The Cloudflare rule, firewall and TLS steps are written in `infra/cloudflare/README.md` but need account/VM access. |
| M2.9 | Every item in [01 Networking and security](01-architecture.md#networking-and-security) checked before the URL is shared | both | ⛔ | Blocked on the external M2.7/M2.8 checks. The repository side is tracked in [12 Security checklist](12-security-checklist.md). |

## M3 · Curated data (weeks 3–5)

| # | Task | Track | Status | Notes |
|---|---|---|---|---|
| M3.1 | `ref_refresh`: airports, runways, aircraft, airlines, countries, H3 → country | A | ✅ | 2026-11-25: monthly (1st, 01:00). Downloads and parses all five datasets, then replaces the tables in one transaction (deletes, updates, inserts); refuses a dataset that halves. Rebuilds `ref.h3_r4_country` for all 288k r4 cells. The newest OpenSky aircraft snapshot is 2025-08 (587k aircraft). Takes over the M1.18 seed; its parsers moved to `orchestrator.refdata`. `infra/test-db.sh` runs it three times on fixtures |
| M3.3 | `flights_sessionizer` (watermark, boundaries, observed arrivals and departures) | A | ✅ | 2026-11-25: Dagster every 5 min on the last 30 min plus 20 min of context; flights open at the first airborne point ([D16](#decided-while-building)); observed `on_ground` and `last_airborne` arrivals and observed departures at the targets; watermark closes and finalises. Logic in `orchestrator.flights` (17 unit tests); `infra/test-db.sh` runs a synthetic landing, takeoff, lost flight and parked aircraft twice |
| M3.4 | `flight_labels_merge` | A | ✅ | 2026-11-25: daily 08:00 for yesterday. Picks the closest OpenSky flight of the same aircraft within 30 min of `first_seen`; observed values win and NULL estimates change nothing. `infra/test-db.sh` runs it twice on the sessionizer's test flights. First live run 2026-11-26 08:00 (the sessionizer has only run since 2026-11-25) |
| M3.5 | `routes_refresh` (OpenSky flight lists) | A | ✅ | 2026-11-25: daily 08:30, rebuilds `ref.callsign_routes` from the last 28 days of flight lists in one transaction; refuses a rebuild that halves the table. No Zenodo fallback ([D17](#decided-while-building)). `infra/test-db.sh` runs it twice, then checks that an empty window is refused |
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

## MK · Cloud & carbon (weeks 4–6)

| # | Task | Track | Status | Notes |
|---|---|---|---|---|
| MK.1 | Kustomize manifests for every service (probes, requests and limits, HPA on public-api, local volumes), `k3s-install.sh`, `k8s-apply.sh`, `deploy.sh` on k3s, `ingest-admin.sh`; CI `k8s` job on a throwaway k3s | A | ✅ | [ADR-0005](adr/0005-single-node-k3s.md). CI `k8s` job green 2026-11-23 (PR #34): deploys twice with no restarts, all four services answer. The db pod runs without containerd's AppArmor profile (it blocked Postgres's own signals). Merged 2026-11-23 |
| MK.2 | Cutover on the VM: `k3s-install.sh`, then `k3s-cutover.sh` (Compose volumes to `/srv/airspace`, deploy, `tailscale serve` to the NodePorts); check the Pi's uploads drain | A | ✅ | 2026-11-23: down 11:37:44–11:45:16 UTC (7.5 min); 16 GB database moved in place; the Pi's spooled batches arrived at 11:49 with none rejected. A cold copy of the pre-cutover database is in `/srv/airspace-precutover` (delete once k3s has run for a week). The next deploy through `deploy.yml` imported no image and restarted no pod. Rollback: `k3s-cutover.sh --rollback` |
| MK.3 | ADR-0006: carbon-aware design (signal, actions, SLOs, measurement) | both | 🟡 | [ADR-0006](adr/0006-carbon-aware-operations.md) proposed 2026-11-23: synthetic day curve with a demo override, Dagster sensor for deferrable jobs with deadlines, a controller pod for the eco profile (public-api HPA cap, slower non-urgent schedules) and SLO probes, CodeCarbon energy × the signal. Waits for Alek's review |
| MK.4 | Simulated carbon-intensity service and its Grafana panel | A | ✅ | `services/carbon` (carbon-signal: deterministic day curve, forecast, demo override, `SIGNAL_TIME_SCALE`), `carbon_readings_record` every 5 min into `ops.carbon_readings`, Grafana *Airspace sustainability* dashboard. Live on the VM since 2026-11-23 (#38); first readings 14:15 UTC |
| MK.5 | gCO₂e per job and per request (CodeCarbon or CPU-time estimate; no power counters on the ARM VM) | A | ⬜ | |
| MK.6 | Carbon-aware controller: Dagster sensor that delays deferrable jobs to a green window before their deadline; eco profiles for services; SLO checks for ingest and the live map | both | ⬜ | |
| MK.7 | Sustainability dashboard: signal, decisions, gCO₂e, SLOs | A | ⬜ | |
| MK.8 | Optional: join the Pi as a k3s agent running only the collector (DaemonSet) | A | ⬜ | Only after MK.2 is stable ([ADR-0005](adr/0005-single-node-k3s.md)) |

## M6 · Portfolio polish (weeks 7–8)

| # | Task | Track | Status | Notes |
|---|---|---|---|---|
| M6.1 | README architecture diagram and demo video | both | ⬜ | |
| M6.2 | Final model cards | B | ⬜ | |
| M6.3 | Final report | both | ⬜ | |

## Stretch

Not started. Only after every M0–M5 "done when" is met, in the order of [10 Stretch](10-roadmap.md#stretch).
