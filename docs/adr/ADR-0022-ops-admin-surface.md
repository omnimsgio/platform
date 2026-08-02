# ADR-0022: Ops Admin Surface

## Status

Accepted — **SQLAdmin v1 Complete / frozen** (`cpaas-sqladmin-v1`)

## Date

2026-08-02

## Context

Operators need a safe way to inspect and manage tenants, API keys, and WhatsApp connections without using tenant Bearer API keys or ad-hoc SQL. The public surface (ADR-0021) must stay contract-first and partner-facing; ops tooling must not blur that boundary.

## Decision

### Path and exposure

- Ops admin lives at `https://api.omnimsg.io/admin/` (gateway → API).
- It is **not** part of the public OpenAPI contract.
- Traefik applies an IP allowlist to `PathPrefix(/admin)` in production.
- Gateway enforces HTTP Basic (`ADMIN_USERNAME` / `ADMIN_PASSWORD`). Tenant API keys are never accepted as admin credentials.
- `/internal/*` remains Docker-network only.

### Read-only mode

- `ADMIN_READ_ONLY=true` enables browse-only operation (incidents / maintenance).
- Enforcement is **server-side**: all mutating HTTP methods and write actions under `/admin` return a deny (e.g. 403). Disabling UI controls alone is insufficient.

### Roles (future)

v1 uses a single Basic principal. ADR reserves future roles without implementing them now:

| Role | Intent |
|------|--------|
| Viewer | Read-only browse (equivalent to `ADMIN_READ_ONLY` for that principal) |
| Operator | Routine ops (key rotate, lifecycle retry) without destructive tenant deletes |
| Admin | Full ops including dangerous confirmations |

### Audit

- Mutations write `admin_audit_events` with actor, action, entity, before/after, `correlation_id` / `request_id`, `request_ip`, `user_agent`, `created_at`.
- Table has indexes on `created_at`, `entity_type`, `entity_id`; migrations include downgrade.

### Lifecycle

- `TenantWhatsappAccount.status` is never freely edited in admin.
- Status changes go only through `omnimsg_common.whatsapp_lifecycle.transition` (ADR-0020).

### Dangerous actions

- Deactivate tenant, API key rotate/disable, WhatsApp lifecycle retry require a confirmation step (implemented with views in Phase C2).

### Phasing

- **C1:** auth, mount, audit schema, read-only enforcement, admin home (DB/Redis/version/contract), runbook. **Done.**
- **C2:** Tenant / ApiKey / WhatsApp / Message views; two-step key rotation with grace period.
  Each view is **deployable alone** (Tenant → ApiKey → WhatsApp → Message); no big-bang C2 merge. **Done.**
- **v1 freeze:** no further admin views or auth changes in this iteration. See [SQLAdmin v2 backlog](../backlog/sqladmin-v2.md) and [closeout](../runbooks/production-admin-sqladmin-v1-closeout-2026-08-03.md).

## Consequences

### Positive

- Clear public vs ops boundary.
- Safe production browsing via `ADMIN_READ_ONLY`.
- Room for RBAC without redesign.

### Negative

- Basic auth is weaker than SSO; OAuth/SSO is a follow-up.
- IP allowlist must be maintained operationally.

### Neutral

- DeliveryAttempt / WebhookEvent admin views wait on persistence models.
