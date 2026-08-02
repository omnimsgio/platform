# Production ops admin (`/admin`)

**ADR:** [ADR-0022](../adr/ADR-0022-ops-admin-surface.md)  
**Host:** `https://api.omnimsg.io/admin/` (Traefik → gateway Basic → API SQLAdmin)

## Configuration

| Env | Purpose |
|-----|---------|
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | HTTP Basic credentials (both required to enable admin) |
| `ADMIN_READ_ONLY` | `true` → server-side deny on all admin writes (403 `admin_read_only`) |
| `ADMIN_ALLOWED_CIDRS` | Traefik `ipallowlist` source ranges for `/admin` (comma-separated) |

Never use tenant API keys as admin credentials.

## Bring-up checklist

1. Set admin secrets + CIDRs in dedicated-hel1 `.env`.
2. `omnimsg-migrate upgrade head` (creates `admin_audit_events`).
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

SQLAdmin UI: `/admin/` — Audit Events (C1); **Tenant** (C2.1); ApiKey / WhatsApp / Message (C2.2–C2.4, each deployable alone).

Production C1 GO evidence: [production-admin-c1-evidence-2026-08-02.md](production-admin-c1-evidence-2026-08-02.md).  
C2.1 Tenant evidence: [production-admin-c2.1-tenant-evidence-2026-08-02.md](production-admin-c2.1-tenant-evidence-2026-08-02.md).

When `ADMIN_READ_ONLY=true`, the API also denies SQLAdmin **action** routes (`/admin/.../action/...`), which are registered as GET but mutate state.

## Security notes

- IP allowlist is mandatory in production; use operator client CIDRs. With Cloudflare orange-cloud, Traefik must use `ipstrategy.depth=1` (already labeled) so allowlist matches `CF` / `X-Forwarded-For` client IP, not the edge hop.
- Default compose falls back to `127.0.0.1/32` if `ADMIN_ALLOWED_CIDRS` unset.
- Future roles (Viewer / Operator / Admin) are reserved in ADR-0022; v1 is a single Basic principal.
- Audit rows: `admin_audit_events` (indexed on `created_at`, `entity_type`, `entity_id`); downgrade supported.
