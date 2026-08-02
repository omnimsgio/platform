# ADR-0020: Tenant WhatsApp Connection Lifecycle

## Status

Accepted — Architecture Locked — **Provisioning Lifecycle v1 Feature Complete** (frozen)

`lifecycle_version = 1` is **frozen**. Do not add statuses or change the v1 state
machine during P3+. New behaviours (e.g. suspended tenant, alternate onboarding)
require `lifecycle_version = 2` (or a superseding ADR), not mutation of this machine.

**Release checklist:** [ADR-0020-lifecycle-v1-release-checklist.md](ADR-0020-lifecycle-v1-release-checklist.md)

### Compatibility Promise

**Provisioning Lifecycle v1 is a public internal contract.** Existing APIs, statuses,
and transition rules must remain compatible for the entire duration of P3 development.
Any incompatible change requires `lifecycle_version = 2`.

### Change Control

Every substantive change to this ADR requires a **new ADR amendment** (or a superseding
ADR / `lifecycle_version = 2`). P3 pull requests must not edit this document or the v1
state machine “along the way.”

### Operational Freeze

Dependency direction is one-way:

`Provisioning → Lifecycle → P3`

P3 may use lifecycle **only as a dependency** (read messaging-ready / `READY` gates).
P3 must never drive lifecycle mutations (`P3 → Lifecycle` is forbidden).

## Date

2026-08-02

## Context

CPaaS v1 onboards tenants via Meta Embedded Signup, then phone registration, webhook subscription, and health checks before messaging. Today `tenant_whatsapp_accounts.status` uses a coarse `pending` → `active` | `error` model, and callers infer readiness from credentials plus ad-hoc checks. That produces early “ready” claims, scattered `if` gates, and no stable recovery/disconnect model.

OmniMsg needs one canonical provisioning workflow so Embedded Signup, provisioning, health, API, portal, gateway, and worker share a single source of truth before production client onboarding.

## Decision

### Single source of truth

WhatsApp integration state lives on **`TenantWhatsappAccount`**:

| Field | Role |
|-------|------|
| `status` | Canonical lifecycle status |
| `status_reason` | Stable machine reason (not free-text) |
| `last_correlation_id` | Correlation id of **every** transition |
| `updated_at` | Time of last lifecycle change |
| `lifecycle_version` | Schema of the state machine (`1` for CPaaS v1) |
| `last_error` | Optional human detail |
| `recovery_target` | Next status when recovering from `ERROR` |

`NOT_CONNECTED` is **virtual** (no row). `tenants.status` and `credit_line_attached` remain orthogonal; credit line does **not** gate messaging readiness on the development path.

### Statuses (`lifecycle_version = 1`)

`NOT_CONNECTED` → `EMBEDDED_SIGNUP_STARTED` → `BUSINESS_CONNECTED` → `PHONE_PENDING` → `WEBHOOK_PENDING` → `HEALTH_CHECK_PENDING` → `READY`

Plus terminals / recovery:

- `ERROR` — provisioning or runtime failure; retry via `recovery_target`
- `DISCONNECTED` — revoke / removed app / deleted phone / detached WABA; reconnect only via Embedded Signup

### Forward-only provisioning workflow

All statuses are **forward-only**, except the **explicitly defined recovery transitions out of `ERROR`**. This lifecycle is a **controlled provisioning workflow**, not a general-purpose state machine. Downgrades such as `READY → PHONE_PENDING` are forbidden.

From `READY` the only exits are:

- `READY → ERROR`
- `READY → DISCONNECTED`

From `DISCONNECTED` the only reconnect path is Embedded Signup (`→ EMBEDDED_SIGNUP_STARTED`).

### Who may mutate status

**Only** these services may change lifecycle status, and **only** via `omnimsg_common.whatsapp_lifecycle.transition()` (or the documented seed/fixture bootstrap helper in that module):

1. Embedded Signup Service
2. Provisioning Service (including `POST /v1/whatsapp/retry` recovery dispatch)
3. Health Service

API handlers, Worker, Gateway, and Portal **read** status; they must not assign `TenantWhatsappAccount.status` directly. CI enforces this with a grep/lint check.

### Messaging readiness

Send and inbound processing are allowed only when `is_messaging_ready(status)` is true. Components must call that helper (or `messaging_ready_statuses()` for SQL filters) — never hard-code `status == "READY"` string compares scattered across the codebase.

P1 Embedded Signup ends at **`PHONE_PENDING`**. P2 owns phone registration, webhook verification, health, retry, and the transition to **`READY`**.

### `READY` entry criteria (`health_ok`)

`HEALTH_CHECK_PENDING → READY` is allowed **only** when the Health Service has verified **all** of the following (deterministic `health_ok`). Any failure moves to `ERROR` with `HEALTH_CHECK_FAILED` (details in `checks` / `last_error`) — never a partial `READY`. When already `READY`, health-check is **idempotent** (confirm only; no status change, no re-provisioning).

| # | Criterion | Meaning |
|---|-----------|---------|
| 1 | Valid business access token | Stored token is present and Graph accepts it (not expired / not revoked) |
| 2 | `waba_id` present | Non-empty WABA id on the account row |
| 3 | `phone_number_id` present | Non-empty phone number id on the account row |
| 4 | Phone registered | Number completed Meta Cloud API registration (PIN/2FA as required) |
| 5 | Webhook verified | App is subscribed to the WABA and subscription/verify checks pass |
| 6 | Graph health check passes | Graph confirms WABA reachable and the attached `phone_number_id` is listed/usable |

**Out of `health_ok` (orthogonal):** `credit_line_attached` — tracked separately; does not block `READY` on the development path (ADR-0018 / SP ops).

**P2 Definition of Done:** a newly onboarded tenant reaches `READY` only via `transition()` after `health_ok`; send and inbound then succeed through `is_messaging_ready()`. **P2 is complete** (P2.1–P2.5): register, webhook, health, retry, E2E/CI golden path.

### P2 implementation constraints (amendment 2026-08-02)

- **Deployable PRs:** each P2 PR must leave the lifecycle consistent without requiring the next PR (P2.1 ends usable at `WEBHOOK_PENDING`, P2.2 at `HEALTH_CHECK_PENDING`, P2.3 at `READY`).
- **Rollback-safe migrations:** new columns are nullable (or safe defaults); rolling deploy must tolerate old app code ignoring new columns.
- **Idempotent provisioning endpoints:** repeat calls after success return 200 without Graph side effects (including health on `READY`).
- **Provisioning lock:** `provisioning_lock_until` prevents parallel register/webhook/health mutations.
- **Deterministic recovery:** `POST /v1/whatsapp/retry` dispatches only via `recovery_target`; response shape matches `GET /v1/whatsapp/connection` (optional `checks`); each retry is audited (`retry_target`, `retry_reason=user`).
- **Step timeout:** `provisioning_step_started_at` records step start; automatic timeout workers are out of P2 scope (design only).
- **Webhook layers:** app-level hub verify (`GET` challenge on gateway) is separate from tenant-level `subscribed_apps` subscribe + Graph confirmation (`POST /v1/whatsapp/provision-webhook`). `webhook_verified_at` is set only after Graph lists `META_APP_ID`.
- **Freeze:** after P2.5, do not extend v1 statuses during P3; use `lifecycle_version = 2` for future lifecycle changes.

### P3 constraints (amendment 2026-08-02 — governance closeout)

- **Inbound must not mutate lifecycle.** Webhook → persist inbound → conversation thread → business logic. Nowhere: `account.status = …` from inbound/worker/gateway.
- **Forbidden in P3:** new lifecycle statuses; edits to `transition()`, `ALLOWED_TRANSITIONS`, or `health_ok`; new provisioning endpoints; edits to this ADR inside a P3 PR.
- **Allowed in P3:** persist inbound messages / conversation thread; read `TenantWhatsappAccount` only via `is_messaging_ready` / `messaging_ready_statuses`; business logic after persistence.
- Needs discovered during P3 that require new lifecycle behaviour go to a **`lifecycle_version = 2`** backlog, not a v1 patch.

## Consequences

### Positive

- One status drives UI badges, support, retry, and automation.
- No premature `READY` before the tenant is operational.
- Disconnect vs error is explicit.
- Future statuses (e.g. `READY_DEGRADED`) change one helper (`lifecycle_version = 2`).
- Clear phase boundary: P2 owns provisioning; P3 owns inbound persistence without touching the state machine.

### Negative

- Existing `active` rows and ES “complete → active” behaviour required a migration and ES refactor.
- v1 freeze means future lifecycle needs (suspend, new onboarding) wait for `lifecycle_version = 2`.

### Neutral

- Aligns with ADR-0018 Solution Partner onboarding; Marketing Domain / Conversation remain deferred or feature-frozen per ADR-0019.
- Phase backlog: P0 Meta ops → P1 ES + lifecycle → P2 provisioning/health (**complete**) → P3 inbound persistence (lifecycle read-only).
- Governance closeout: [lifecycle v1 release checklist](ADR-0020-lifecycle-v1-release-checklist.md).
