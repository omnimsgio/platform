# App Review evidence — `business_management`

**Phase:** 1 (Meta Dashboard — permission + token + test call + App Review)  
**Product:** OmniMsg / FinestAR  
**Kickoff tracker:** `/opt/stacks/ops/omnimsgio-meta-sp-kickoff.md`  
**Runbook:** `docs/providers/meta-whatsapp-solution-partner.md`

## Identifiers

| Field | Value |
|-------|--------|
| Graph API version | `v21.0` (target for Phase 1 test calls) |
| App ID | `3492919917530282` (OmniMsg) |
| Business ID | `1329905112443890` (Finestar Hospitality) |
| System User | `omnimsg_api` (id `122113353693380836`) |
| Datum pre-checka | 2026-08-02 |
| Datum test callova | **2026-08-02** (USER token w/ BM for App Review counter; SYSTEM_USER regen still pending) |
| Endpointi | `/me/businesses`, `/{business-id}?fields=id,name`, `/{business-id}/owned_whatsapp_business_accounts` — all HTTP 200; see `graph-response.json` |

---

## 0. Pre-check (2026-08-02) — PASS

Completed **before** regenerating the system user token with `business_management`.

| Check | Expected | Result | Evidence |
|-------|----------|--------|----------|
| App has `business_management` assigned | Permission on OmniMsg app / Testing use cases | **PASS** | Meta Dashboard Testing use cases lists `business_management` — **0 of 1** API call(s) required (hard blocker for use-case counter; permission is present). WhatsApp scopes already have enough calls; `manage_app_solution` Completed. |
| Permission visible in App Dashboard | Visible in Permissions / use case testing | **PASS** | Same Testing use cases row for `business_management`. |
| System User role on portfolio | Admin **or** Finance editor | **PASS** | Kickoff §2: **omnimsg_api** — **Admin** on Business portfolio (2026-07-28); App role Administrator on OmniMsg; Full control on Test WABA. Admin satisfies Phase 1 pre-check. *Note: credit-line attach (Phase 2) still prefers Finance editor capability — Admin covers BM ops; reconfirm before Phase 2.* |
| Business Verification | Approved for Business `1329905112443890` | **PASS** | Kickoff §1: **Business verification Approved** (seen on Tech Provider onboarding 2026-07-21). Portfolio marked verified in §2 assets. |

### Business Portfolio check (kickoff / evidence)

| Check | Status / note |
|-------|----------------|
| Business ID | `1329905112443890` |
| Business name | Finestar Hospitality |
| Business Verification | **Approved** (2026-07-21) |
| System user role | **Admin** (`omnimsg_api`) — meets Admin \| Finance editor bar |
| Solution Partner status | **Blocked / In progress** (kickoff §1) — public MBP form ineligible; WhatsApp SP + credit line channel still open. App Review for BM can proceed without SP; **credit line will not work** until SP + Extended Credit are live. |
| Extended Credit Line | **Not provisioned** — record ID when available; **not** a Phase 1 test-call blocker |

### Current system token identity (pre-regen, 2026-08-02)

Graph `debug_token` against live `META_BUSINESS_ACCESS_TOKEN` (local `.env`):

| Field | Value |
|-------|--------|
| `app_id` | `3492919917530282` (OmniMsg) — **match** |
| `type` | `SYSTEM_USER` |
| `application` | OmniMsg |
| `is_valid` | `true` |
| `expires_at` | `0` (Never) |
| System user | `omnimsg_api` (`122113353693380836`) |
| Scopes present | `whatsapp_business_management`, `whatsapp_business_messaging`, `manage_app_solution`, `whatsapp_business_manage_events`, `public_profile` |
| `business_management` in scopes | **Absent** — expected until Phase 1 token regen |

Probe calls without BM scope (expected failures; confirms token identity + missing scope):

- `GET /{business-id}?fields=id,name,verification_status` → OAuth `#200` *Requires business_management permission*
- `GET /me/businesses` → OAuth `#100` *Missing Permission*
- `GET /me` → OK (`omnimsg_api`)

**Next step after this pre-check:** regenerate system user token with existing WhatsApp scopes **plus** `business_management`; keep old token for rollback; sync local + `dedicated-hel1` `.env`.

---

## 2. Graph test calls (2026-08-02) — PASS

| Call | Endpoint | HTTP | Result |
|------|----------|------|--------|
| A | `GET /v21.0/me/businesses?fields=id,name` | 200 | Fine Star, Finestar Hospitality, stay.hr |
| B | `GET /v21.0/1329905112443890?fields=id,name` | 200 | Finestar Hospitality |
| C | `GET /v21.0/1329905112443890/owned_whatsapp_business_accounts` | 200 | stay_hr, Test WABA, Finestar Hospitality WABA |

Evidence: `graph-response.json` (no access token).  
**Token used for counter:** temporary **USER** token (Ante Vrcan) with `business_management` — **not** written to `.env`.  
**Still required:** regenerate **omnimsg_api** SYSTEM_USER token with BM for production.

Meta Dashboard **Testing use cases** may lag up to **24h** before showing `business_management` **1 of 1** / Completed.

---

## Definition of Done tracking (Phase 1)

- [x] Pre-check portfolio + app BM permission + system user role + verification
- [x] Graph test calls A/B/(C) HTTP 200 — awaiting Dashboard counter 0→1 (up to 24h)
- [ ] `business_management` test call = 1/1 (or Completed) on Testing use cases
- [ ] Advanced Review submitted for `business_management`
- [ ] `business_management` visible in `omnimsg_api` SYSTEM_USER `debug_token` scopes (with WA management + messaging)
- [ ] SYSTEM_USER `debug_token` confirms expected App ID + Business (same token in `.env` / prod)
- [x] This `notes.md` has Graph API version, App ID, Business ID + test-call date
- [ ] Kickoff tracker updated
- [ ] Runbook §3 updated
- [x] `graph-response.json` archived; screenshots / use-case / video still pending

**Screencast + use-case copy:** [screencast-script.md](screencast-script.md) — record Graph Explorer A/B/C + upload to Allowed usage.

Phase 1 closes on **submit**. Do **not** start Phase 2 (credit-line attach) until Meta Advanced Approval **and** Extended Credit Line exist.
