# Cloudflare setup (M2.7/M2.8)

No Cloudflare token is stored in this repository. These are the console/API actions that make the
public deployment match `docs/01-architecture.md#networking-and-security` and
`docs/12-security-checklist.md`.

## Pages project

- Project: `airspace-live-tracker`
- Repository: `airspace-monitor/airspace-live-tracker`, root directory `web`
- Build command: `pnpm build`
- Output directory: `dist`
- Production branch: `main`
- Preview deployments: every pull request; the API CORS regex already permits
  `*.airspace-live-tracker.pages.dev`.

The repository can also deploy with `.github/workflows/pages.yml`. It uses direct upload and skips
the deploy step until these GitHub secrets exist:

| Name | Purpose |
|---|---|
| `CLOUDFLARE_API_TOKEN` | Pages:Edit for this account |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account id |
| `VITE_CARTO_KEY` | CARTO basemap key (client-side; restrict by domain) |
| `VITE_API_BASE` (repository **variable**) | `https://api.<domain>/api/v1` |

`web/wrangler.toml` pins the Pages project and `dist` output. The API URL is baked into the static
bundle at build time, so a preview and production build must both receive it.

## API CORS

On the VM, add the production origin and the preview regex to `infra/.env`:

```dotenv
CORS_ALLOWED_ORIGINS=https://<domain>,https://airspace-live-tracker.pages.dev
CORS_ALLOWED_ORIGIN_REGEX=https://([a-z0-9-]+\.)?airspace-live-tracker\.pages\.dev
```

`infra/k8s-apply.sh` copies those into the `airspace-env` secret, and `infra/k8s/public-api.yaml`
passes them to the API. The API also has a 60 request / 10 s in-memory limiter keyed by
`CF-Connecting-IP`; the edge rule below remains the first line of defense.

## Edge rate limit

Create a Cloudflare rate-limiting rule for the public API:

- Expression:
  `(http.host eq "api.<domain>" and starts_with(http.request.uri.path, "/api/v1/"))`
- Requests: **60**
- Period: **10 seconds**
- Action: block (or managed challenge); return the API's JSON error shape if a custom response is
  configured.
- Key: client IP.

This matches the API limiter and the limit in `docs/01-architecture.md`.

## Firewall

The target is TCP **443** inbound only from Cloudflare's published IP ranges; port **22** is closed
to the internet and SSH is over Tailscale. Update the OCI security list (or the equivalent network
firewall) after the Caddy/Origin CA step, then verify from a non-tailnet host that 443 answers only
through Cloudflare and 22 does not answer at all.

## TLS and DNS

- Proxy `api`, `ingest` and `grafana`; SSL mode **Full (strict)**.
- Install the Cloudflare Origin CA certificate on the VM (Caddy); the certificate is not in git.
- Keep `api`/`ingest`/`grafana` proxied.

## Verification

1. `curl -I https://<domain>` and the Pages URL: expect the security headers from
   `web/public/_headers`.
2. Browser preflight from the production origin and from a preview URL succeeds.
3. A request from an origin outside the allow-list has no `Access-Control-Allow-Origin`.
4. The 61st request in 10 s from one IP gets `429` with `Retry-After`.
5. From outside the tailnet: 443 answers, 22 does not.
6. `docs/12-security-checklist.md` has no ⬜ rows before sharing the URL.
