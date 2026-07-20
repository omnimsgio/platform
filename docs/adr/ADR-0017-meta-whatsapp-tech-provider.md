# ADR-0017: Meta WhatsApp Tech Provider as Primary v1 Channel Path

## Status

Superseded by [ADR-0018](ADR-0018-meta-whatsapp-solution-partner.md)

## Date

2026-07-20

## Context

OmniMsg ([omnimsg.io](https://omnimsg.io), FinestAR) needs a concrete first channel and Meta partnership model. Meta offers Solution Partner (reseller) and Tech Provider paths. Reseller economics and ownership of WABAs do not match the platform’s multi-tenant, API-first product: tenants should own their WhatsApp Business Accounts while OmniMsg provides Embedded Signup, Cloud API messaging, and webhook processing behind a unified API.

## Decision

OmniMsg will pursue the **[Meta WhatsApp Tech Provider](https://developers.facebook.com/documentation/business-messaging/whatsapp/solution-providers/get-started-for-tech-providers)** path as the **primary v1 channel path** — not Solution Partner reseller.

Implications:

- **Embedded Signup** onboards client businesses onto WABAs under the Tech Provider model (implemented in **api** / **channels** / portal phases — not foundation).
- **App Review** and required WhatsApp / Business permissions are platform milestones before production traffic.
- **Webhook verification and ingress** land at `apps/gateway`, then flow through versioned events into the execution engine (`webhook.inbound.received` and delivery updates).
- **Multi-tenant messaging** uses Meta Cloud API with per-tenant credentials and WABA configuration (ADR-0007, ADR-0004).
- Other channels and vendors remain in scope for the platform vision but are secondary to this WhatsApp Tech Provider vertical slice for v1.

## Consequences

### Positive

- Clear GTM and engineering focus for the first vertical slice.
- Aligns with multi-tenant ownership: clients keep WABAs; OmniMsg is the integration and messaging layer.
- Matches existing ADRs (API-first, provider abstraction, event-driven webhooks).

### Negative

- Meta App Review, business verification, and Embedded Signup UX are external dependencies on the critical path to production WhatsApp.
- Early WhatsApp semantics may bias contracts; capability model (ADR-0008) must keep other channels expressible.

### Neutral

- ~~Solution Partner / reseller is explicitly out of v1 strategy; revisiting would require a new ADR.~~ **Superseded:** partnership model revised in [ADR-0018](ADR-0018-meta-whatsapp-solution-partner.md) (Solution Partner + credit line).
