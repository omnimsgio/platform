# OmniMsg

**[omnimsg.io](https://omnimsg.io)** — API-first omnichannel messaging platform.

Built by **[FinestAR](https://finestar.hr/)**.

> One API. Any channel. Any provider.

Customers integrate once with a stable HTTP API. OmniMsg routes messages across channels and providers without requiring client-side changes when vendors or routes change.

## Go-to-market (v1)

OmniMsg is positioning as a [Meta WhatsApp Solution Partner](https://developers.facebook.com/documentation/business-messaging/whatsapp/solution-providers/get-started-for-solution-partners): credit line toward Meta, clients do not enter a Meta payment method, and FinestAR invoices WhatsApp usage plus platform. Embedded Signup, webhooks, and multi-tenant WABA messaging (business tokens + credit-line sharing) form the first vertical slice via Meta Cloud API. See [ADR-0018](docs/adr/ADR-0018-meta-whatsapp-solution-partner.md) and the [Solution Partner runbook](docs/providers/meta-whatsapp-solution-partner.md).

## Vision

One API.
Any channel.
Any provider.

Planned channels include WhatsApp Business, SMS, email, RCS, push, and webhooks — behind a shared provider abstraction.

## Status

**Foundation** — documentation, ADRs, contracts, app skeletons, and shared-infra wiring (Postgres `omnimsgio`, Redis DB `3`, Traefik labels).

## Local development (shared infra)

OmniMsg Compose runs **only** `gateway` / `api` / `worker`. Postgres, Redis, and Traefik come from shared stacks — do not add those services here (ADR-0016).

### Prerequisites

| Stack | Path | Bring-up |
|-------|------|----------|
| data | `/opt/stacks/data` | `docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build` |
| redis | `/opt/stacks/redis` | `docker compose -f docker-compose.yml -f docker-compose.local.yml up -d` |
| traefik | `/opt/stacks/traefik` | already up on Docker network `proxy` |

Apps attach to external networks `proxy`, `data_default`, and `redis_default`. Hostnames: `postgis:5432`, `infra-redis:6379` (logical Redis DB **3**).

### Provision Postgres

```bash
cp .env.example .env   # set DATABASE_URL password (never commit .env)
./scripts/provision-local-db.sh
```

Creates database/role `omnimsgio` on the existing `postgis` container with grants limited to that database.

### Run apps

```bash
docker compose -f docker/development/docker-compose.yml --env-file .env up -d --build
```

Gateway is published via Traefik Host `omnimsgio.localhost` (entrypoints `web` / `websecure`, service port `8000`).

```bash
# Ensure Host resolves (RFC 6761 .localhost → 127.0.0.1; use --resolve if needed)
curl -fsS --resolve omnimsgio.localhost:80:127.0.0.1 http://omnimsgio.localhost/health
# Local Traefik redirects HTTP→HTTPS:
curl -kfsS --resolve omnimsgio.localhost:443:127.0.0.1 https://omnimsgio.localhost/health
```

Dashboard: `http://127.0.0.1:8080`. If HTTPS returns 403, the local Traefik CrowdSec bouncer has no LAPI — disable it for Desktop (see Traefik `dynamic/` local overrides) or curl the gateway container directly.

### CI

GitHub Actions (`.github/workflows/ci.yml`) runs Ruff, pytest smoke tests, and an OpenAPI file presence check. It does not start Traefik, Postgres, or Redis.

```bash
pip install -e ".[dev]"
ruff check apps packages tests
pytest -q
```

## Docs

- [North Star](docs/NORTH_STAR.md) — vision, architecture, v1 scope, implementation status
- [Architecture Decision Records](docs/adr/) — accepted platform decisions (ADR-0001–0018)
- [Meta WhatsApp Solution Partner runbook](docs/providers/meta-whatsapp-solution-partner.md) — Meta Business ops (App Review, tokens, credit line); kickoff tracker: `/opt/stacks/ops/omnimsgio-meta-sp-kickoff.md`
