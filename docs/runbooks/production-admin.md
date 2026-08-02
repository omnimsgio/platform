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

SQLAdmin UI: `/admin/` (Audit Events view in C1; Tenant/ApiKey/WhatsApp/Message in C2).

## Security notes

- IP allowlist is mandatory in production; default compose falls back to `127.0.0.1/32` if unset.
- Future roles (Viewer / Operator / Admin) are reserved in ADR-0022; v1 is a single Basic principal.
- Audit rows: `admin_audit_events` (indexed on `created_at`, `entity_type`, `entity_id`); downgrade supported.
