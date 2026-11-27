# 12 · M2 security checklist

M2.9 is the gate before a public URL is shared. This file records what is already enforced by the
repository and what still needs a Cloudflare/VM action. It is deliberately not marked complete:
the external checks can only be signed off after they are applied and verified on the real
deployment.

Legend: ✅ in the repository and tested · 🟡 code/config present, deployment action pending ·
⬜ not applied yet.

| Concern | Requirement | Repository state | Remaining action |
|---|---|---|---|
| Public API CORS | Only the production origin and Pages previews may call `/api/v1/*`; GET/POST; `Content-Type`; no credentials | ✅ `services/api` `CORSMiddleware`, origins from `CORS_ALLOWED_ORIGINS`, preview regex `CORS_ALLOWED_ORIGIN_REGEX`; tests cover allowed/denied/preview and 429 CORS | Set the production domain in `infra/.env` and confirm with a browser preflight |
| Edge rate limit | 60 requests / 10 s per IP on `api.<domain>/api/v1/*` | 🟡 API has an in-memory 60/10 s `FixedWindowRateLimiter` keyed by `CF-Connecting-IP`, with `429` + `Retry-After`; edge rule not created | Create the Cloudflare rate-limiting rule in `infra/cloudflare/README.md` |
| Firewall | TCP 443 inbound only from Cloudflare; port 22 closed to the internet | ⬜ no OCI/Cloudflare changes applied from this repo | Update the OCI security list and verify from an external host; SSH only over Tailscale |
| TLS at origin | Cloudflare Full (strict), Origin CA certificate in Caddy | ⬜ external | Install the certificate on the VM and set SSL mode |
| DNS and edge | `api`, `ingest`, `grafana` proxied records | ⬜ external; domain is still open decision O5 | Create the records after O5 is decided |
| Collector auth | Random key, argon2id hash, bearer token | ✅ existing ingest-api/admin CLI | Rotate only through the admin CLI if needed |
| DB exposure | No NodePort; only in-cluster access and SSH/Tailscale admin | ✅ existing k3s manifests/service | Re-check NodePorts after the next deploy |
| DB roles | Least privilege per service | ✅ existing migrations/roles | Re-run the role checks after migrations |
| Grafana | Anonymous access disabled; Dashboards only | ✅ existing Grafana provisioning | Verify externally only after M1.2 |
| Secrets | No secrets in git; VM `.env`; Actions secrets for Tailscale/deploy | ✅ `.gitignore`, `.env.example` placeholders | Add `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `VITE_CARTO_KEY`; set `VITE_API_BASE` repository variable |
| Pages headers | Clickjacking/MIME/referrer/permissions protections | ✅ `web/public/_headers` | Confirm headers on the deployed `pages.dev` URL |
| CARTO key | Client key restricted by domain/origin; not committed | ✅ local `web/.env`, fallback without key | Restrict the key in CARTO and add it to the Pages environment |

The public URL must not be shared until every ⬜ row is checked on the real deployment. The Pages
preview URLs are intentionally allowed by the API CORS regex, but they are not a public launch.
