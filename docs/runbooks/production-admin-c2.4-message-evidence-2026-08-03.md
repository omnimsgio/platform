# Production evidence — Ops admin C2.4 (Messages read-only)

**Host:** `api.omnimsg.io` `/admin` (dedicated-hel1)  
**Date:** 2026-08-03  
**Commit:** `91cb755` (`feat(admin): C2.4 Message read-only observability view`)

## Smoke

| Check | Result |
|-------|--------|
| `GET /admin/message/list` without auth | **401** |
| Same with Basic (allowlisted IP) | **200** |
| UI title Messages | **yes** |
| Filters present (Tenant / Status / …) | **yes** |
| No “New Message” / delete actions | **yes** |

## Scope closed (SQLAdmin v1)

- C2.1 Tenant  
- C2.2 ApiKey (+ rotation checkpoint)  
- C2.3 WhatsApp Accounts  
- C2.4 Messages (this)

No further admin scope in this iteration.
