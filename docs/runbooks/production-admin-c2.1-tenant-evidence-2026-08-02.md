# Production evidence — Ops admin C2.1 (Tenant view)

**Host:** `api.omnimsg.io` `/admin` (dedicated-hel1)  
**Date:** 2026-08-02  
**Commit:** `a112249` (`feat(admin): C2.1 Tenant SQLAdmin view with audit and confirm actions`)

## Checks

| Check | Result |
|-------|--------|
| `GET /admin/tenant/list` without auth | **401** |
| `GET /admin/home` with Basic | **200** |
| `GET /admin/tenant/list` with Basic (allowlisted IP) | **200**; UI shows Tenants, Activate/Deactivate, existing rows |
| Deploy | rsync (no `.env`) → rebuild `omnimsgio-apps:prod` → recreate `api`/`gateway`/`worker` |

## Notes

- No schema migration required for C2.1.
- `ADMIN_READ_ONLY` now also denies SQLAdmin `/admin/.../action/...` GET mutators (covered by unit tests; prod currently `ADMIN_READ_ONLY=false`).
- Next independently deployable view: **ApiKey** (C2.2).
