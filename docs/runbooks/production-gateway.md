# Production gateway (`api.omnimsg.io`)

Deploy target: **dedicated-hel1** Traefik on Docker network `proxy` (not local WSL).

Public surface is locked by [ADR-0021](../adr/ADR-0021-public-api-surface.md).

Production GO evidence (2026-08-02): [production-openapi-surface-evidence-2026-08-02.md](production-openapi-surface-evidence-2026-08-02.md). Baseline tag: `cpaas-openapi-surface-v1`.

## Bring-up

```bash
# On dedicated-hel1, from /opt/stacks/omnimsgio
cp .env.example .env   # set secrets — never commit
./scripts/provision-local-db.sh
docker compose -f docker/production/docker-compose.yml --env-file .env up -d --build
# migrations + seed (WhatsApp fields when META_* set):
./scripts/seed-local-tenant.sh
```

Compose: [`docker/production/docker-compose.yml`](../../docker/production/docker-compose.yml) — Traefik `Host(\`api.omnimsg.io\`)`, entrypoint `websecure`, `tls.certresolver=lecf`, service port `8000`.

Set `APP_ENV=production` in server `.env`. Image build args `GIT_SHA` / `BUILD_DATE` populate `/version`.

## Public URL checklist

| URL | Expect |
|-----|--------|
| `https://api.omnimsg.io/` | Discovery JSON (`status`, `contract_version`, docs links) |
| `https://api.omnimsg.io/version` | `version`, `git_sha`, `build_date`, `environment` |
| `https://api.omnimsg.io/health` | Gateway **liveness** only (`status`/`version`) |
| `https://api.omnimsg.io/v1/health` | API **readiness** (`checks.database` / `checks.redis`); no Bearer |
| `https://api.omnimsg.io/openapi.json` | Contract SSOT; `ETag` + `Cache-Control: public, max-age=300` |
| `https://api.omnimsg.io/docs` | Swagger UI |
| `https://api.omnimsg.io/redoc` | ReDoc |
| `https://api.omnimsg.io/v1/messages` without Bearer | `401` |

`/internal/*` must not be reachable on the public host (API-only Docker network).

### Verify after deploy

```bash
curl -sS https://api.omnimsg.io/ | jq .
curl -sS https://api.omnimsg.io/version | jq .
curl -sSI https://api.omnimsg.io/openapi.json | grep -iE 'etag|cache-control'
curl -sS -o /dev/null -w '%{http_code}\n' https://api.omnimsg.io/docs
curl -sS https://api.omnimsg.io/health
curl -sS https://api.omnimsg.io/v1/health
```

Gateway **refuses to start** if `packages/contracts/openapi/openapi.yaml` is missing or invalid (`OPENAPI_CONTRACT_PATH` in the image).

## Health semantics

| Path | Meaning |
|------|---------|
| `/health` | Process alive (Traefik / LB). No DB or Redis. |
| `/v1/health` | API readiness. `200` when DB + Redis OK; `503` when either fails. `worker` / `provider` keys reserved (may be `null`). |

## Security headers checklist

Gateway should send on responses:

- [ ] `X-Content-Type-Options: nosniff`
- [ ] `Referrer-Policy: no-referrer`
- [ ] `X-Frame-Options: DENY`
- [ ] `Content-Security-Policy` on `/docs` and `/redoc` (Swagger/ReDoc CDN allowlist)

## Meta webhook

| Item | Value |
|------|--------|
| Callback URL | `https://api.omnimsg.io/webhooks/meta/whatsapp` |
| Verify token | Same as `META_VERIFY_TOKEN` in server `.env` |
| App secret | `META_APP_SECRET` in server `.env` (signature check) |

Configured (2026-07-20): callback URL + verify token + `messages` field; test WABA subscribed to OmniMsg app. Ops status: `/opt/stacks/ops/omnimsgio-meta-sp-kickoff.md`.

Subscribed field checklist + Dashboard Test sample payloads: [docs/meta/webhooks/notes.md](../meta/webhooks/notes.md).

## Required server env

- `DATABASE_URL` — Postgres role/DB `omnimsgio` on shared `postgis`
- `REDIS_URL` — `redis://infra-redis:6379/3` (key prefix `omnimsgio:`)
- `META_VERIFY_TOKEN`, `META_APP_SECRET`
- `APP_ENV=production`
- Optional seed: `META_WABA_ID`, `META_PHONE_NUMBER_ID`, `META_BUSINESS_ACCESS_TOKEN`
