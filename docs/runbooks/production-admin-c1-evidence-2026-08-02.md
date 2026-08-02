# Production evidence: Ops Admin C1 (2026-08-02)

**Host:** `api.omnimsg.io` `/admin` (dedicated-hel1)  
**ADR:** [ADR-0022](../adr/ADR-0022-ops-admin-surface.md)  
**Decision:** Phase C1 ops admin infrastructure — **GO / production verified**

## Deploy

- Image rebuilt with `sqladmin`, `admin.py`, migration `008_admin_audit_events`.
- `ADMIN_USERNAME=omnimsg_ops`, password stored only on server `.env` (not in git).
- `ADMIN_ALLOWED_CIDRS` = ops workstation IPv4 `/32`.
- Traefik middleware: `ipallowlist` + `ipstrategy.depth=1` (Cloudflare trusted forwarded headers already on entrypoints).

## Verification matrix

| Check | Result |
|-------|--------|
| No `Authorization` (allowlisted IP) | **401** + `WWW-Authenticate` |
| Wrong Basic | **401** |
| Correct Basic | **200** `/admin/home` |
| IP outside allowlist (`203.0.113.1/32` lock) | Traefik **403 Forbidden** |
| `ADMIN_READ_ONLY=true` POST/PUT/PATCH/DELETE | **403** `error.code=admin_read_only` |
| Audit row fields | action, entity_type/id, correlation_id, request_id, request_ip, user_agent, created_at |
| `/admin/home` secrets | no postgres/redis URLs, tokens, or passwords |
| Migration `008` downgrade → upgrade | table dropped then recreated |

## Notes

- Allowlist must use the **client** IP as seen after Cloudflare (`ipstrategy.depth=1`). Curling from the origin host itself uses the server egress IP, not the operator laptop IP.
- Rotate `ADMIN_PASSWORD` after shared debugging sessions; never commit it.
- Phase **C2** (Tenant / ApiKey / WhatsApp / Message views) may start after this GO.
