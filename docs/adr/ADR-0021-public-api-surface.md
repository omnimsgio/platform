# ADR-0021: Public API Surface

## Status

Accepted

## Date

2026-08-02

## Context

`api.omnimsg.io` is the public edge for OmniMsg. Without an explicit surface map, implementers risk exposing FastAPI runtime schemas, internal auth resolve routes, or conflating load-balancer liveness with dependency readiness. Partners, SDKs, and ops need a stable, contract-backed set of public paths.

## Decision

The **public HTTP surface** on `api.omnimsg.io` (Traefik → `apps/gateway`) is:

| Path | Auth | Role |
|------|------|------|
| `GET /` | public | Discovery JSON (`status`, versions, links) |
| `GET /version` | public | Build metadata (`version`, `git_sha`, `build_date`, `environment`, `contract_version`) |
| `GET /health` | public | **Gateway process liveness** only (no DB/Redis) |
| `GET /openapi.json` | public | OpenAPI document from contract SSOT |
| `GET /docs` | public | Swagger UI bound to `/openapi.json` |
| `GET /redoc` | public | ReDoc bound to `/openapi.json` |
| `GET /v1/health` | public | **API readiness** (see below) |
| `/v1/*` (other) | Bearer API key | Tenant API (proxied to `apps/api`) |
| `/webhooks/meta/whatsapp` | Meta hub / signature | Provider ingress |
| `/internal/*` | **never public** | Docker-network only on `apps/api` |

### Contract SSOT

- Source of truth: `packages/contracts/openapi/openapi.yaml` (ADR-0005).
- The gateway **must not** serve FastAPI auto-generated OpenAPI for the public docs surface.
- `info.x-contract-version` is the compatibility pin echoed as `contract_version` on discovery and `/version`.
- Gateway **fail-fast** on startup if the contract file is missing or not valid OpenAPI YAML.

### Caching

- `GET /openapi.json` returns `Cache-Control: public, max-age=300` and an `ETag`.
- Matching `If-None-Match` yields `304 Not Modified`.

### Health semantics

- `/health` — edge/process alive for Traefik and load balancers.
- `/v1/health` — API readiness. Response includes `checks.database` and `checks.redis` (required). Keys `checks.worker` and `checks.provider` are reserved in the contract; they may be `null` until implemented. Overall `status` is `ok` when required checks pass; otherwise `error` with HTTP 503.

### Correlation

- Clients may send `X-Correlation-Id`. Errors include `error.correlation_id` (ADR-0015). The gateway echoes `X-Correlation-Id` on responses when available.

### Security headers

Gateway responses include at least: `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `X-Frame-Options: DENY`. `/docs` and `/redoc` use a CSP that allows required Swagger/ReDoc CDN assets.

## Consequences

### Positive

- Clear boundary between public API, edge docs, and internal routes.
- Partners and SDKs consume one contract; ops get distinct liveness vs readiness.
- Invalid contracts cannot ship as a “healthy” gateway.

### Negative

- Expanding `/v1/health` checks requires OpenAPI updates and careful backward compatibility.
- Public docs expose the full tenant API shape (by design).

### Neutral

- Admin UI and SDK generation remain separate follow-ups; they must not invent paths outside this surface without amending this ADR.
