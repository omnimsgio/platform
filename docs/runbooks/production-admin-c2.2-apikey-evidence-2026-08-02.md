# Production evidence — Ops admin C2.2 (ApiKey view)

**Host:** `api.omnimsg.io` `/admin` (dedicated-hel1)  
**Date:** 2026-08-02  
**Commit:** `63ec5de` (`feat(admin): C2.2 ApiKey view with timed two-step rotation`)

## Deploy

- rsync (no `.env`) → build `omnimsgio-apps:prod`
- Migration: `008_admin_audit_events → 009_api_key_rotation`
- `ADMIN_API_KEY_GRACE_HOURS=24` set on hel1
- Recreate `api` / `gateway` / `worker`

## Smoke

| Check | Result |
|-------|--------|
| `GET /admin/api-key/list` without auth | **401** |
| `GET /admin/api-key/list` with Basic (allowlisted IP) | **200** |
| UI shows Start rotation / Finish rotation / Deactivate | **yes** |
| `key_hash` / 64-char hex not in list HTML | **yes** |

## Tests (pre-deploy)

- `tests/test_api_key_lifecycle.py` — second rotation blocked, finish without rotation, cannot deactivate replacement mid-grace, old key unusable after grace, both valid during grace, finish revokes old
- `tests/test_admin_c2_apikey.py` — list hides hash, create reveals once, rotate reveal 410 on refresh, finish audits

## Checkpoint (before C2.3)

Do **not** start WhatsApp admin until ops confirms:

1. Audit rows for create / rotate_start / rotate_finish / deactivate look correct
2. No security concerns on plaintext-once / hash hiding
3. A dry-run rotation on a non-critical tenant key completes without downtime (both keys valid during grace)
