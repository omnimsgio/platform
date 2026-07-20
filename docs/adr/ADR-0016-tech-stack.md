# ADR-0016: Tech Stack

## Status

Accepted

## Date

2026-07-20

## Context

Foundation needs a single, coherent runtime for `gateway`, `api`, and `worker` so the monorepo stays operable without premature polyglot complexity. Stack choices must support HTTP APIs, async workers, multi-tenant data, and a queue for event-driven delivery (ADR-0002, ADR-0006, ADR-0009). Postgres, Redis, and Traefik already run as shared stacks under `/opt/stacks/{data,redis,traefik}`; OmniMsg should consume them rather than bundle duplicate Compose services.

## Decision

OmniMsg foundation uses one runtime and the following stack:

| Layer | Choice |
|-------|--------|
| Language | Python 3.12 |
| HTTP | FastAPI + Uvicorn |
| Apps | `gateway`, `api`, `worker` (same stack) |
| Database | PostgreSQL / PostGIS via shared data plane (database `omnimsgio`) |
| Queue | Redis via shared data plane (logical DB index `3`, key prefix e.g. `omnimsgio:`) |
| Edge | Traefik via shared proxy plane |
| Config | Environment-based (ADR-0009) |
| Observability | OpenTelemetry stub hooks only in this phase (no full observability Compose stack yet; ADR-0011 remains the long-term target) |

Portal remains a placeholder. SDKs stay outside foundation.

### Shared infrastructure (not bundled)

Local and production **data / queue / edge** planes come from the shared `/opt/stacks` stacks — **not** from OmniMsg Compose. OmniMsg `docker-compose` runs **only** application containers (`gateway`, `api`, `worker`) and attaches them to **external** Docker networks.

| Concern | Shared stack | Path | Container / notes |
|---------|--------------|------|-------------------|
| Database | data | `/opt/stacks/data` | `postgis` — hostname `postgis:5432`; provision DB/role `omnimsgio` only (do not alter other databases) |
| Queue | redis | `/opt/stacks/redis` | `infra-redis` — hostname `infra-redis:6379`, Redis DB `3` |
| Edge | traefik | `/opt/stacks/traefik` | Traefik on network `proxy`; app labels route e.g. `omnimsgio.localhost` → gateway |

OmniMsg Compose **must not** define or start Postgres, Redis, or Traefik services. Expected external networks: `proxy`, `data_default`, `redis_default`.

Bring-up of shared stacks is a prerequisite (see each stack’s `AGENTS.md` / compose files). Production follows the same pattern (shared `proxy` / host networks later; not OmniMsg-owned Postgres/Redis/Traefik).

## Consequences

### Positive

- One language and framework across edge, API, and workers reduces cognitive and CI load.
- FastAPI aligns with contract-first HTTP surfaces and OpenAPI generation later.
- Postgres and Redis cover tenancy persistence and async event fan-out for v1.
- Reuses existing PostGIS, Redis, and Traefik instead of duplicating infra per product Compose file.

### Negative

- Polyglot or specialized runtimes (e.g. Go gateway) are deferred; revisiting later has migration cost.
- OTel remains stubbed until a later observability phase, so production-grade tracing is not foundation-complete.
- Local/dev depends on shared stacks being up and networked; OmniMsg alone cannot bring up the full data plane.

### Neutral

- Per-app or workspace `pyproject.toml` layout is an implementation detail as long as the monorepo stays Python-centric.
- Exact Redis key-prefix and Traefik Host labels are implementation details within the shared-infra boundary above.
