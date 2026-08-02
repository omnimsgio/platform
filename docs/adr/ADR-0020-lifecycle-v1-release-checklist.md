# Provisioning Lifecycle v1 — Release Checklist

Companion to [ADR-0020](ADR-0020-tenant-whatsapp-connection-lifecycle.md).

**Date:** 2026-08-02  
**Verdict:** Provisioning Lifecycle v1 is **Feature Complete / frozen**. P3 may proceed using lifecycle only as a dependency.

## Checklist

| Stavka | Status | Evidencija |
|--------|--------|------------|
| ADR-0020 Architecture Locked + Feature Complete | Done | [ADR-0020](ADR-0020-tenant-whatsapp-connection-lifecycle.md) Status |
| Compatibility Promise (v1 is a stable behaviour contract during P3) | Done | ADR-0020 Compatibility Promise; [CONTRIBUTING](../../CONTRIBUTING.md) |
| Change Control (ADR-0020 changes only via ADR amendment / `lifecycle_version = 2`) | Done | CONTRIBUTING Architecture Locked; no silent P3 edits to ADR-0020 |
| Status / transition tests | Done | `tests/test_whatsapp_lifecycle.py` + P2 suite |
| `transition()` sole status mutator | Done | `scripts/check-whatsapp-lifecycle-ssot.sh` + CI |
| Messaging gate via `is_messaging_ready` / `messaging_ready_statuses` | Done | gateway / worker |
| Golden path in CI | Done | `.github/workflows/ci.yml` → `test_golden_path_not_connected_to_ready_retry_ready` |
| Recovery / retry tests | Done | `tests/test_provisioning_retry.py`, e2e fail+retry |
| Idempotent provisioning endpoints | Done | register / webhook / health (+ READY re-health) |
| Provisioning lock | Done | register + webhook lock 409; health lock in code |
| OpenAPI aligned with implementation | Done | connection, register-phone, provision-webhook, health-check, retry |
| Operational Freeze (P3 uses lifecycle only as dependency) | Done | ADR-0020 Operational Freeze; CONTRIBUTING |
| CI SSOT check remains mandatory | Done | `.github/workflows/ci.yml` → `check-whatsapp-lifecycle-ssot.sh` |

## Known non-blocking follow-up

- Dedicated health-check `provisioning_lock_until` conflict (409) test — lock behaviour exists in code; a focused unit/API test is optional hygiene and **does not** block this freeze.

## Review gates for P3

1. No P3 PR may change [ADR-0020](ADR-0020-tenant-whatsapp-connection-lifecycle.md).
2. No P3 PR may add lifecycle statuses, edit `transition()` / `ALLOWED_TRANSITIONS` / `health_ok`, or add provisioning endpoints.
3. Inbound path may **read** messaging-ready status only; never write `TenantWhatsappAccount.status`.
4. Incompatible lifecycle behaviour requires `lifecycle_version = 2` (new/superseding ADR), not a v1 patch.
