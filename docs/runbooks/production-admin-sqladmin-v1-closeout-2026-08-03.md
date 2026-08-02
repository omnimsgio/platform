# Production closeout — SQLAdmin v1 (frozen)

**Host:** `api.omnimsg.io` `/admin` (dedicated-hel1)  
**Baseline tag:** `cpaas-sqladmin-v1`  
**ADR:** [ADR-0022](../adr/ADR-0022-ops-admin-surface.md)  
**Decision:** Ops admin Phase C1–C2 — **Complete / frozen**

## v1 scope (do not expand in this iteration)

| Capability | Evidence |
|------------|----------|
| C1 infrastructure | [production-admin-c1-evidence-2026-08-02.md](production-admin-c1-evidence-2026-08-02.md) |
| C2.1 Tenant | [production-admin-c2.1-tenant-evidence-2026-08-02.md](production-admin-c2.1-tenant-evidence-2026-08-02.md) |
| C2.2 ApiKey | [production-admin-c2.2-apikey-evidence-2026-08-02.md](production-admin-c2.2-apikey-evidence-2026-08-02.md) |
| C2.2 rotation checkpoint | [production-admin-c2.2-rotation-checkpoint-2026-08-03.md](production-admin-c2.2-rotation-checkpoint-2026-08-03.md) |
| C2.3 WhatsApp Accounts | [production-admin-c2.3-whatsapp-evidence-2026-08-03.md](production-admin-c2.3-whatsapp-evidence-2026-08-03.md) |
| C2.4 Messages (read-only) | [production-admin-c2.4-message-evidence-2026-08-03.md](production-admin-c2.4-message-evidence-2026-08-03.md) |

## Horizontal controls (v1)

- HTTP Basic + Traefik IP allowlist (`ipstrategy.depth=1` behind Cloudflare)
- `ADMIN_READ_ONLY` server-side deny (including SQLAdmin `/action/` GET mutators)
- `admin_audit_events` with indexes + downgrade
- Confirmations for dangerous actions
- Sensitive-data masking (API keys once, WhatsApp tokens, message recipients/payload)
- Lifecycle SSOT / AST guards (ADR-0020)

## Freeze rule

New admin views, roles, auth changes, or dashboards belong in **SQLAdmin v2 backlog** only. Do not mix into v1 PRs.

## Next platform focus (outside admin)

1. Embedded Signup / onboarding polish  
2. Messaging API stabilisation  
3. Webhook lifecycle  
4. SDK generation  
5. Partner documentation  
6. First external tenant  
