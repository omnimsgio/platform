# ADR-0018: Meta WhatsApp Solution Partner as Primary v1 Channel Path

## Status

Accepted

## Date

2026-07-20

## Context

ADR-0017 chose the Meta WhatsApp **Tech Provider** path so tenants would own WABAs while Meta billed clients directly. That model conflicts with OmniMsg’s commercial intent: FinestAR wants a **credit line toward Meta**, to **invoice clients** for WhatsApp usage (plus platform fees), and to avoid requiring clients to attach a payment method at Meta.

Meta’s [Solution Partner](https://developers.facebook.com/documentation/business-messaging/whatsapp/solution-providers/get-started-for-solution-partners) path supports credit-line sharing, partner-managed billing economics, Embedded Signup, and Cloud API messaging on client WABAs. Multi-tenant API ownership of WABA configuration remains compatible; what changes is who pays Meta and how tokens/credit lines are provisioned.

## Decision

OmniMsg will pursue the **[Meta WhatsApp Solution Partner](https://developers.facebook.com/documentation/business-messaging/whatsapp/solution-providers/overview)** path as the **primary v1 channel path**, superseding ADR-0017.

Implications:

- **Billing:** OmniMsg holds a Meta **credit line**, shares it with onboarded client WABAs, and **invoices clients** for usage + platform. Clients do **not** enter a Meta payment method.
- **Embedded Signup** (or Hosted ES) onboards client businesses; optional partner-initiated WABA where Meta allows. Code exchange yields **business access tokens** for messaging those WABAs.
- **App Review (Advanced access)** for `whatsapp_business_management` and `whatsapp_business_messaging` (plus `whatsapp_business_manage_events` only if MM API + CAPI are in scope) is a platform milestone before production traffic.
- **One Meta app** and **one webhook callback URL** (verify + signature at `apps/gateway`); subscribe WABAs and register phones after ES.
- **System user token** with **Finance editor** role for credit-line sharing; **business tokens** from ES for day-to-day Cloud API send/receive on client WABAs.
- **Multi-tenant config** stores per-tenant WABA id, phone_number_id, business access token, and credit-line attached flag (ADR-0007, ADR-0004).
- Ops detail lives in the Solution Partner runbook; adapter / ES / billing implementation remains **api** / **channels** / later phases — not foundation code in this decision.

## Consequences

### Positive

- Aligns GTM with desired economics: charge clients, pay Meta via credit line.
- Clear engineering focus for the first vertical slice (WhatsApp Cloud API + ES + webhooks).
- Matches existing ADRs (API-first, provider abstraction, event-driven webhooks, multi-tenant).

### Negative

- Becoming a Solution Partner (MBP approval, credit line, Direct Support) is an **external critical path**; production onboarding with credit line waits on Meta approval even if Cloud API / ES / webhooks are built on a development app in parallel.
- App Review, ToS acceptance in WhatsApp Manager, phone registration PIN/2FA, and credit-line sharing are additional operational dependencies versus Tech Provider billing-by-Meta.
- Partner billing product (usage → client invoices vs Meta cost) is OmniMsg-owned work, not a Meta feature.

### Neutral

- ADR-0017 is superseded; Tech Provider is no longer the v1 partnership model.
- Other channels and vendors remain in platform vision but secondary to this WhatsApp Solution Partner vertical slice for v1.
