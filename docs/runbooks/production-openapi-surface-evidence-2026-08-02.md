# Production evidence: OpenAPI surface (2026-08-02)

**Host:** `api.omnimsg.io` (dedicated-hel1)  
**Baseline tag:** `cpaas-openapi-surface-v1`  
**ADR:** [ADR-0021](../adr/ADR-0021-public-api-surface.md)  
**Decision:** Phase A + Phase B OpenAPI edge surface — **Completed / production GO**

## Deploy notes

- Image `omnimsgio-apps:prod` rebuilt with `packages/contracts` copied into `/app/packages/contracts/openapi/openapi.yaml`.
- `APP_ENV=production`, `OPENAPI_CONTRACT_PATH=/app/packages/contracts/openapi/openapi.yaml`.
- Gateway startup log: `contract=/app/packages/contracts/openapi/openapi.yaml version=1.0.0` (fail-fast OK).

## Smoke results

| Check | Result |
|-------|--------|
| `GET /` discovery | 200; `status=ok`, `environment=production`, `contract_version=1.0.0` |
| `GET /version` | 200; version / git_sha / build_date / environment / contract_version |
| `GET /health` | 200; edge liveness only |
| `GET /v1/health` | 200; `checks.database=true`, `checks.redis=true`, `worker`/`provider` null |
| `GET /openapi.json` | 200; `ETag` present; `Cache-Control: public, max-age=300` |
| `If-None-Match` → 304 | Pass |
| `GET /docs` | 200; Swagger; CSP + `X-Content-Type-Options` / `X-Frame-Options` / `Referrer-Policy` |
| `GET /redoc` | 200 |
| `POST /v1/messages` without Bearer | 401 |
| `POST /internal/v1/auth/resolve` on public host | 404 (not exposed) |
| Contract SSOT | `info.x-contract-version=1.0.0`; not FastAPI runtime schema |

## CI gates (repo)

- `scripts/check-openapi-lint.sh` (`openapi-spec-validator`)
- `scripts/check-openapi-parity.sh` (YAML `/v1` ↔ API routes)
- `scripts/smoke-openapi-runtime.sh` (uvicorn curl smoke)

## Closeout

Phase A (edge docs surface) and Phase B (parity + CI + ADR-0021) are **complete**. Next capability work: Ops Admin (ADR-0022 / Phase C1–C2), then SDKs.
