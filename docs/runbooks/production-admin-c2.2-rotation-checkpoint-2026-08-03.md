# Production checkpoint — ApiKey two-step rotation (C2.2)

**Host:** `api.omnimsg.io` (dedicated-hel1)  
**Date:** 2026-08-03 (00:44–00:45 Europe/Zagreb)  
**Tenant:** `ten_es_smoke` (non-critical)  
**Actor:** `omnimsg_ops`  
**Result:** **PASS — ApiKey lifecycle production-verified**

C2.3 remains closed until an explicit GO after this checkpoint.

## Sequence

### 1. Create baseline

| Check | Result |
|-------|--------|
| Created key via SQLAdmin for `ten_es_smoke` | `key_cc1b30abbdeb42198adec6925dd62ff0` |
| Auth resolve | **200** → `tenant_id=ten_es_smoke`, matching `api_key_id` |
| Audit `apikey_create` | **yes** — `corr=req_c22_ckpt_20260802T224412Z`, IP `46.188.247.89`, UA present, actor `omnimsg_ops` |

### 2. Start rotation

| Check | Result |
|-------|--------|
| Admin **Start rotation** | **307** → `/admin/api-key/reveal` |
| Plaintext shown once | **200** with `omni_…` |
| Refresh reveal | **410 Gone** (“no longer available”) |
| Audit `apikey_rotate_start` | **yes** — `corr=req_c22_ckpt_rotate_20260802T224434Z` |
| New key | `key_2beecafdc8b0454eaeaabb998b6cb6b6` |
| Grace | `ADMIN_API_KEY_GRACE_HOURS=24` → `grace_expires_at` ~2026-08-03T22:44:34Z |

### 3. Grace window (both keys)

| Key | 3× resolve |
|-----|------------|
| Old `key_cc1b30…` | **200** / correct `api_key_id` |
| New `key_2beecaf…` | **200** / correct `api_key_id` |

Audit total stayed small (create/rotate only — no flood from auth).

### 4. Finish rotation

| Check | Result |
|-------|--------|
| Admin **Finish rotation** on old key | **307** |
| Audit `apikey_rotate_finish` | **yes** — `corr=req_c22_ckpt_finish_20260802T224510Z`, IP + UA + actor |
| Old DB status | `inactive` |
| New DB status | `active` |
| Old auth after finish | **401** |
| New auth after finish | **200** |

### 5. Post-grace (time simulation)

Started a second rotation on the then-active key, set `grace_expires_at` to the past in DB (no Finish yet):

| Check | Result |
|-------|--------|
| Old key after simulated grace | **401** |
| New key after simulated grace | **200** |
| Cleanup | `finish_rotation` on old; final key authenticates |

### 6. Audit field completeness (checkpoint chain)

For `key_cc1b30abbdeb42198adec6925dd62ff0`:

| action | correlation_id | IP | UA | actor | timestamp |
|--------|----------------|----|----|-------|-----------|
| `apikey_create` | `req_c22_ckpt_20260802T224412Z` | yes | yes | omnimsg_ops | yes |
| `apikey_rotate_start` | `req_c22_ckpt_rotate_20260802T224434Z` | yes | yes | omnimsg_ops | yes |
| `apikey_rotate_finish` | `req_c22_ckpt_finish_20260802T224510Z` | yes | yes | omnimsg_ops | yes |

No plaintext or `key_hash` in audit `after` payloads (public snapshot only).

## Ops note

Redirect `Location` after rotate-start used internal host `http://omnimsgio-api:8000/...` behind Traefik; public follow requires rewriting to `https://api.omnimsg.io/...`. Reveal still worked with the session cookie once the public URL was used. Non-blocking for GO; fix in a follow-up if desired.

## Decision

**ApiKey lifecycle is production-verified.**  
**C2.3 TenantWhatsappAccount may open only after explicit GO** (constraint already agreed: all status changes via `transition` / ADR-0020 only).
