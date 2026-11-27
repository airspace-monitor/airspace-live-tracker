# Airspace Monitor — web

React 19 + TypeScript (strict) + Vite single-page app. The app has the
layout, live header stats, the Events feed with cursor paging and map fly-to,
the aircraft map with smooth motion, hover/selection, trails and the aircraft
card, the attribution footer and the mobile bottom sheet. Briefing, Ask and
Arrivals remain placeholders until M4/M5.

```
web/
├── src/api/          fetch client, types and TanStack Query hooks
├── src/components/   layout, tabs, panels and the lazily loaded map pane
├── src/hooks/        media query, clock tick, SSE connection
├── src/lib/          config, panel definitions, formatters
├── src/styles/       design tokens and global CSS (Tailwind v4)
└── src/test/         Vitest setup
```

## Commands

```bash
pnpm install
pnpm dev          # http://localhost:5173
pnpm typecheck
pnpm lint
pnpm test:run
pnpm build
```

## API

The dev server proxies `/api` to the tailnet API, so the browser makes
same-origin requests and CORS is not involved locally. The default target is
`http://airspace-vm.tailf5a9a6.ts.net:8001`; copy `.env.example` to `.env` and
change `VITE_API_PROXY_TARGET` to point somewhere else (for example a locally
running `public-api`).

The production app calls `https://api.<domain>/api/v1` through Cloudflare. Set
the build-time `VITE_API_BASE` repository variable to that URL; the API allows
the Pages origins in M2.8. Locally, the proxy keeps the browser same-origin.

## Deployment

Cloudflare Pages project `airspace-live-tracker`, root `web`, build `pnpm build`,
output `dist`. `.github/workflows/pages.yml` deploys production from `main` and
a preview from each PR once `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`
exist. Set `VITE_CARTO_KEY` as a Pages secret and `VITE_API_BASE` as a repository
variable (or the Pages environment). `web/public/_headers` carries the security
headers; see `docs/12-security-checklist.md`.

## Basemap

CARTO Dark Matter is the target basemap. Put `VITE_CARTO_KEY` in `web/.env`
(git-ignored) to use it:

```dotenv
VITE_CARTO_KEY=your-key
```

Without a key the app falls back to OpenFreeMap Dark, so development still
works. Never commit the key; set it in the Cloudflare Pages environment for
production, and restrict it in the CARTO dashboard. The footer attribution
switches between CARTO and OpenFreeMap automatically.

## Scope

`docs/08-frontend.md` is the visual and behavioural spec. M2.4 is the shell
only: no MapLibre/deck.gl, no events paging, no fly-to and no real
Briefing/Ask/Arrivals content yet.
