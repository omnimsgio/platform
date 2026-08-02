# P3 — Inbound Message Persistence (plan stub)

**Status:** Ready to open (separate from Lifecycle v1 freeze)  
**Depends on:** Provisioning Lifecycle v1 Feature Complete — [release checklist](../adr/ADR-0020-lifecycle-v1-release-checklist.md)

## Goal

Persist inbound WhatsApp messages and conversation thread after the gateway accepts a Meta webhook for a messaging-ready tenant.

```text
Webhook → Persist inbound message → Conversation thread → Business logic
```

## Hard constraints (from ADR-0020 freeze)

- Lifecycle is a **read-only dependency** (`Provisioning → Lifecycle → P3`).
- Never write `TenantWhatsappAccount.status` from inbound / worker / gateway.
- Do **not** edit ADR-0020, `transition()`, `ALLOWED_TRANSITIONS`, `health_ok`, or add provisioning endpoints in P3 PRs.
- Incompatible lifecycle needs → backlog `lifecycle_version = 2`.
- ConversationReferral / Conversation marketing extensions remain **feature frozen** (ADR-0019); keep no-referral quality gate.

## Likely touchpoints (to refine in full P3 plan)

- Worker `inbound_message` path (`apps/worker`) — today referrals + outbound delivery status only
- Message / thread schema (`packages/common` models + migration)
- Contracts / events as needed (`packages/contracts`)
- Gateway remains HMAC → tenant resolve via `messaging_ready_statuses()` → queue (no lifecycle writes)

## Out of scope

- Lifecycle / provisioning / health / retry
- Marketing Domain, CAPI, Ads, Conversation Identity
