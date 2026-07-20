# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- API-phase vertical slice: Alembic schema (`tenants`, `api_keys`, `messages`), `scripts/seed-local-tenant.sh`, gateway Bearer API-key auth via `POST /internal/v1/auth/resolve`, Redis fixed-window rate limits, message persist + idempotency, `GET /v1/messages/{id}`, worker stub delivery updates (`message.delivery_updated.v1`), and `packages/providers` ABC/stub
- OpenAPI Bearer security scheme plus `GET /v1/messages/{id}`; CI Postgres/Redis services for migrations and integration tests
- Foundation app skeletons: `gateway` (Traefik-facing `/health`), `api` (`/v1/health`, stub `POST /v1/messages` → Redis DB 3), `worker` (queue consumer stub), and `packages/common` settings
- Contracts seed: OpenAPI (`GET /v1/health`, `POST /v1/messages`), ADR-0015 error shape, events `message.queued.v1` / `message.delivery_updated.v1` / `webhook.inbound.received.v1`, plus request/response examples
- GitHub Actions CI: Ruff, pytest smoke, OpenAPI presence (no shared-infra dependency)
- Shared-infra wiring: Postgres DB/role `omnimsgio` (`scripts/provision-local-db.sh`), Redis DB `3` on shared redis stack, app-only Compose on external `proxy` / `data_default` / `redis_default` with Traefik Host `omnimsgio.localhost`
- ADR-0016 notes that local/prod data plane comes from shared `/opt/stacks/{data,redis,traefik}` (OmniMsg Compose does not run those services)
- Platform repository skeleton (apps, packages, infrastructure, docs)
- Architecture Decision Records ADR-0001 through ADR-0017
- ADR index and template in `docs/adr/README.md`
- ADR-0016 tech stack (Python/FastAPI, PostgreSQL, Redis)
- ADR-0017 Meta WhatsApp Tech Provider as primary v1 channel path
- North Star and README product positioning (omnimsg.io, FinestAR, Tech Provider GTM)
- Root configuration and community files (LICENSE, CONTRIBUTING, SECURITY, `.env.example`, `pyproject.toml`, etc.)
- GitHub templates and CODEOWNERS

### Removed

- Empty duplicate `docs/decisions/` (ADRs live in `docs/adr/`)
