# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Ops admin C1 (ADR-0022): `/admin` Basic auth at gateway, SQLAdmin mount, `admin_audit_events` (indexes + downgrade), `ADMIN_READ_ONLY` server-side write deny, `/admin/home` readiness chips, Traefik IP allowlist, [production-admin](docs/runbooks/production-admin.md) runbook

### Changed

- GTM pivot to Meta WhatsApp **Solution Partner** (ADR-0018): credit line toward Meta, OmniMsg invoices clients; ADR-0017 Tech Provider path superseded
- North Star, README, and ADR index updated for Solution Partner GTM; Solution Partner ops runbook and SP technical milestones documented
- North Star: Meta SP / App Review / credit line marked **In progress** (ops kickoff tracked outside the repo)
- North Star Implementation Status: Meta webhook ingress, `tenant_whatsapp_accounts`, WhatsApp Cloud API adapter, and worker inbound/outbound marked Done / In progress for channels slice

### Added

- Public web: `apps/web` Next.js promo (`omnimsg.io` / `www`) + portal shell (`app.omnimsg.io`); Traefik/`lecf` compose; Cloudflare DNS; runbook `docs/runbooks/production-web.md`
- Production Compose: `docker/production/` Traefik `Host(\`api.omnimsg.io\`)` + `lecf` TLS, Meta webhook runbook note; package Alembic migration data for `omnimsg-migrate` in installed image
- Channels slice: `tenant_whatsapp_accounts` + seed from Meta env; gateway `GET`/`POST /webhooks/meta/whatsapp` (hub verify, HMAC, inbound enqueue); `packages/providers/whatsapp` Meta Cloud API adapter; worker outbound WhatsApp + inbound `message_status` delivery updates
- Tests for Meta signature/hub challenge, Graph request shape (httpx mock), webhook → inbound queue, and outbound WhatsApp with mocked Graph API
- Meta SP/MBP ops kickoff: runbook kickoff status, `.env.example` `META_VERIFY_TOKEN` / `META_APP_SECRET`, out-of-repo tracker `/opt/stacks/ops/omnimsgio-meta-sp-kickoff.md`
- ADR-0018 Meta WhatsApp Solution Partner as primary v1 channel path
- Runbook `docs/providers/meta-whatsapp-solution-partner.md` (assets, App Review, tokens, credit line, tech milestones)
- API-phase vertical slice: Alembic schema (`tenants`, `api_keys`, `messages`), `scripts/seed-local-tenant.sh`, gateway Bearer API-key auth via `POST /internal/v1/auth/resolve`, Redis fixed-window rate limits, message persist + idempotency, `GET /v1/messages/{id}`, worker stub delivery updates (`message.delivery_updated.v1`), and `packages/providers` ABC/stub
- OpenAPI Bearer security scheme plus `GET /v1/messages/{id}`; CI Postgres/Redis services for migrations and integration tests
- Foundation app skeletons: `gateway` (Traefik-facing `/health`), `api` (`/v1/health`, stub `POST /v1/messages` → Redis DB 3), `worker` (queue consumer stub), and `packages/common` settings
- Contracts seed: OpenAPI (`GET /v1/health`, `POST /v1/messages`), ADR-0015 error shape, events `message.queued.v1` / `message.delivery_updated.v1` / `webhook.inbound.received.v1`, plus request/response examples
- GitHub Actions CI: Ruff, pytest smoke, OpenAPI presence (no shared-infra dependency)
- Shared-infra wiring: Postgres DB/role `omnimsgio` (`scripts/provision-local-db.sh`), Redis DB `3` on shared redis stack, app-only Compose on external `proxy` / `data_default` / `redis_default` with Traefik Host `omnimsgio.localhost`
- ADR-0016 notes that local/prod data plane comes from shared `/opt/stacks/{data,redis,traefik}` (OmniMsg Compose does not run those services)
- Platform repository skeleton (apps, packages, infrastructure, docs)
- Architecture Decision Records ADR-0001 through ADR-0017 (ADR-0018 added under Changed / Added above)
- ADR index and template in `docs/adr/README.md`
- ADR-0016 tech stack (Python/FastAPI, PostgreSQL, Redis)
- ADR-0017 Meta WhatsApp Tech Provider as primary v1 channel path *(later superseded by ADR-0018)*
- North Star and README product positioning (omnimsg.io, FinestAR; GTM later pivoted to Solution Partner)
- Root configuration and community files (LICENSE, CONTRIBUTING, SECURITY, `.env.example`, `pyproject.toml`, etc.)
- GitHub templates and CODEOWNERS

### Removed

- Empty duplicate `docs/decisions/` (ADRs live in `docs/adr/`)

## [cpaas-openapi-surface-v1] — 2026-08-02

Baseline tag for the public OpenAPI edge on `api.omnimsg.io` (ADR-0021). Production smoke: [docs/runbooks/production-openapi-surface-evidence-2026-08-02.md](docs/runbooks/production-openapi-surface-evidence-2026-08-02.md).

### Added

- Gateway public surface: `GET /` discovery, `GET /version`, contract-backed `GET /openapi.json` (ETag + `Cache-Control: public, max-age=300` + 304), `/docs`, `/redoc`
- Fail-fast OpenAPI contract load in gateway lifespan; `packages/contracts` copied into Docker images
- Public `GET /v1/health` readiness (database + redis checks); edge `GET /health` remains process liveness
- ADR-0021 Public API Surface; `info.x-contract-version: "1.0.0"`; `X-Correlation-Id` documented on errors
- CI: `openapi-spec-validator` lint, `/v1` path/method parity, runtime curl smoke for docs/openapi
- Security headers on gateway (`X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`, CSP on docs)

### Changed

- API `/v1/health` response shape to readiness envelope (`status`, `version`, `checks`)
- North Star: OpenAPI surface marked Done (production); CPaaS baseline `cpaas-openapi-surface-v1`
