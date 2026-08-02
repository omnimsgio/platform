# P3 — Inbound Message Persistence

**Status:** Implemented (P3.1–P3.5)  
**Depends on:** Provisioning Lifecycle v1 Feature Complete — [release checklist](adr/ADR-0020-lifecycle-v1-release-checklist.md) · baseline `cpaas-lifecycle-v1`

## Goal

Persist inbound WhatsApp messages and conversation threads after the gateway accepts a Meta webhook for a messaging-ready tenant.

```text
Webhook → Persist inbound message → Conversation thread → Domain event
```

## Behaviour

- Extend `messages` with `direction`, `from_address`, `conversation_id`, `provider_message_id`
- Canonical thread key: `(tenant_id, channel, contact_external_id)`
- Conversation upsert + Message insert in **one transaction**
- Emit `message.inbound.received.v1` **only after COMMIT** and only for new inserts
- Duplicate `provider_message_id` → `ON CONFLICT DO NOTHING` (immutable payload / audit row)
- Same `correlation_id`: Gateway → Redis → Worker → Message → event
- Thread API: `GET /v1/conversations/{id}/messages` oldest → newest (read-only)

## Hard constraints (ADR-0020 freeze)

- Lifecycle is a **read-only dependency**
- Never write `TenantWhatsappAccount.status` from inbound / worker / gateway
- Do **not** edit ADR-0020, `transition()`, `ALLOWED_TRANSITIONS`, `health_ok`, or add provisioning endpoints
- ConversationReferral marketing extensions remain **feature frozen** (ADR-0019)

## Out of scope

- Media download / CDN, auto-replies, bots, agent assignment
- Conversation Identity, Marketing Domain, CAPI, Ads
- Message update/delete APIs
