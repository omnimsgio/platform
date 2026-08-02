# Production ops admin (`/admin`)

**ADR:** [ADR-0022](../adr/ADR-0022-ops-admin-surface.md)  
**Host:** `https://api.omnimsg.io/admin/` (Traefik → gateway Basic → API SQLAdmin)

## Configuration

| Env | Purpose |
|-----|---------|
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | HTTP Basic credentials (both required to enable admin) |
| `ADMIN_READ_ONLY` | `true` → server-side deny on all admin writes (403 `admin_read_only`) |
| `ADMIN_ALLOWED_CIDRS` | Traefik `ipallowlist` source ranges for `/admin` (comma-separated) |
| `ADMIN_API_KEY_GRACE_HOURS` | Hours the old key stays valid after **Start rotation** (default `24`, max `168`) |

Never use tenant API keys as admin credentials.

## Bring-up checklist

1. Set admin secrets + CIDRs in dedicated-hel1 `.env`.
2. `omnimsg-migrate upgrade head` (includes `admin_audit_events`, `009_api_key_rotation`).
3. Rebuild/recreate `api` + `gateway`.
4. From an allowlisted IP:

```bash
curl -sS -u "$ADMIN_USERNAME:$ADMIN_PASSWORD" https://api.omnimsg.io/admin/home
curl -sS -o /dev/null -w '%{http_code}\n' -u "$ADMIN_USERNAME:$ADMIN_PASSWORD" \
  https://api.omnimsg.io/admin/
```

5. Without credentials → `401` with `WWW-Authenticate: Basic`.
6. With `ADMIN_READ_ONLY=true`, `POST` under `/admin` (except login) → `403`.

## Home

`GET /admin/home` shows DB / Redis / app version / environment / contract version / read-only flag.

SQLAdmin UI: `/admin/` — Audit Events (C1); **Tenant** (C2.1); **API Keys** (C2.2); **WhatsApp Accounts** (C2.3); **Messages** (C2.4).

**SQLAdmin v1 status: Complete / frozen** — baseline tag `cpaas-sqladmin-v1`; [closeout](production-admin-sqladmin-v1-closeout-2026-08-03.md). New ideas → [SQLAdmin v2 backlog](../backlog/sqladmin-v2.md).

### Messages (C2.4)

- Strictly read-only list/detail (no create/edit/delete/actions).
- List: created_at, tenant, channel/provider, direction, status, recipient (masked), correlation_id.
- Detail: timestamps, ids, redacted payload (tokens/phones/emails), derived error / provider response when present in payload.
- Filters: tenant, status, channel, direction, created_at (operators).

### WhatsApp accounts (C2.3)

- Read-mostly list/details; `business_access_token` masked (`••••` + last 4).
- No create/edit/delete of credentials or free-form status.
- **Retry provisioning** (ERROR only) → `RetryService` → `transition()`.
- **Mark disconnected** (READY only) → `transition(..., DISCONNECTED)`.
- CI: `scripts/check-whatsapp-lifecycle-ssot.sh` + `test_admin_whatsapp_source_never_assigns_status_directly`.

### API Key rotation (C2.2)

1. Select an active key → **Start rotation** (confirmation) → copy the new plaintext once.
2. Both keys authenticate until `grace_expires_at` (`ADMIN_API_KEY_GRACE_HOURS`).
3. Select the **old** key → **Finish rotation** to revoke it (or wait for grace expiry — auth rejects the old key automatically).
4. Audit actions: `apikey_create`, `apikey_rotate_start`, `apikey_rotate_finish`, `apikey_deactivate`.

Production C1 GO evidence: [production-admin-c1-evidence-2026-08-02.md](production-admin-c1-evidence-2026-08-02.md).  
C2.1 Tenant evidence: [production-admin-c2.1-tenant-evidence-2026-08-02.md](production-admin-c2.1-tenant-evidence-2026-08-02.md).  
C2.2 ApiKey evidence: [production-admin-c2.2-apikey-evidence-2026-08-02.md](production-admin-c2.2-apikey-evidence-2026-08-02.md).  
C2.2 rotation checkpoint (**PASS**): [production-admin-c2.2-rotation-checkpoint-2026-08-03.md](production-admin-c2.2-rotation-checkpoint-2026-08-03.md).  
C2.3 WhatsApp evidence: [production-admin-c2.3-whatsapp-evidence-2026-08-03.md](production-admin-c2.3-whatsapp-evidence-2026-08-03.md).  
C2.4 Message evidence: [production-admin-c2.4-message-evidence-2026-08-03.md](production-admin-c2.4-message-evidence-2026-08-03.md).  
SQLAdmin v1 closeout: [production-admin-sqladmin-v1-closeout-2026-08-03.md](production-admin-sqladmin-v1-closeout-2026-08-03.md).

When `ADMIN_READ_ONLY=true`, the API also denies SQLAdmin **action** routes (`/admin/.../action/...`), which are registered as GET but mutate state.

## Security notes

- IP allowlist is mandatory in production; use operator client CIDRs. With Cloudflare orange-cloud, Traefik must use `ipstrategy.depth=1` (already labeled) so allowlist matches `CF` / `X-Forwarded-For` client IP, not the edge hop.
- Default compose falls back to `127.0.0.1/32` if `ADMIN_ALLOWED_CIDRS` unset.
- Future roles (Viewer / Operator / Admin) are reserved in ADR-0022; v1 is a single Basic principal.
- Audit rows: `admin_audit_events` (indexed on `created_at`, `entity_type`, `entity_id`); downgrade supported.
