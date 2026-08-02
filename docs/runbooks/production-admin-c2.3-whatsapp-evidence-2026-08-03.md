# Production evidence — Ops admin C2.3 (WhatsApp Accounts)

**Host:** `api.omnimsg.io` `/admin` (dedicated-hel1)  
**Date:** 2026-08-03  
**Commits:**
- `fe03011` — public Location / forwarded host (pre-C2.3 follow-up)
- `8087478` — C2.3 WhatsApp Accounts view

## Smoke

| Check | Result |
|-------|--------|
| `GET /admin/tenant-whatsapp-account/list` without auth | **401** |
| Same with Basic (allowlisted IP) | **200** |
| UI: Retry provisioning / Mark disconnected | **yes** |
| No `EAAG…` / long token leak in list HTML | **yes** |
| Redirect `Location` uses public host | **yes** — `https://api.omnimsg.io/admin/tenant-whatsapp-account/list?...` (not `omnimsgio-api`) |

## Guards

- Mutations only via `transition()` / `RetryService` (no direct `.status =` in admin module)
- CI: `scripts/check-whatsapp-lifecycle-ssot.sh` + AST test in `tests/test_admin_c2_whatsapp.py`

## Next

C2.4 Message read-only view (independent deploy).
