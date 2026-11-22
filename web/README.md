# Airspace Monitor — web

React 19 + TypeScript (strict) + Vite single-page app. The shell (M2.4) has the
layout, live header stats, the Events feed, the attribution footer and the
mobile bottom sheet. The map and the remaining panels come next.

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

The production app will call `https://api.<domain>/api/v1` through Cloudflare;
CORS is added there in M2.8.

## Scope

`docs/08-frontend.md` is the visual and behavioural spec. M2.4 is the shell
only: no MapLibre/deck.gl, no events paging, no fly-to and no real
Briefing/Ask/Arrivals content yet.
