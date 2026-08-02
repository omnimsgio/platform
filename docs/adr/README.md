# Architecture Decision Records

Accepted decisions that shape OmniMsg. Propose changes via [RFCs](../rfcs/) when an ADR is not yet appropriate.

Product context: [omnimsg.io](https://omnimsg.io) · [FinestAR](https://finestar.hr/) · [North Star](../NORTH_STAR.md)

**Architecture Locked:** When an ADR’s Status includes *Architecture Locked*, PRs that change that area must include a new ADR, an ADR amendment, or an explicit confirmation that the change only implements the existing decision — see [CONTRIBUTING.md](../../CONTRIBUTING.md#architecture-locked-review-rule).

## Index

| ADR | Title |
|-----|--------|
| [ADR-0001](ADR-0001-platform-vision.md) | Platform Vision |
| [ADR-0002](ADR-0002-monorepo.md) | Monorepo Structure |
| [ADR-0003](ADR-0003-api-first.md) | API-First Design |
| [ADR-0004](ADR-0004-provider-abstraction.md) | Provider Abstraction and Execution Engine |
| [ADR-0005](ADR-0005-contract-first.md) | Contract-First Architecture |
| [ADR-0006](ADR-0006-event-driven-architecture.md) | Event-Driven Architecture |
| [ADR-0007](ADR-0007-multi-tenant.md) | Multi-Tenant by Default |
| [ADR-0008](ADR-0008-provider-capability-model.md) | Provider Capability Model |
| [ADR-0009](ADR-0009-configuration-strategy.md) | Configuration Strategy |
| [ADR-0010](ADR-0010-versioning-strategy.md) | Versioning Strategy |
| [ADR-0011](ADR-0011-observability.md) | Observability |
| [ADR-0012](ADR-0012-security-model.md) | Security Model |
| [ADR-0013](ADR-0013-provider-lifecycle.md) | Provider Lifecycle |
| [ADR-0014](ADR-0014-data-ownership.md) | Data Ownership |
| [ADR-0015](ADR-0015-error-model.md) | Error Model |
| [ADR-0016](ADR-0016-tech-stack.md) | Tech Stack |
| [ADR-0017](ADR-0017-meta-whatsapp-tech-provider.md) | Meta WhatsApp Tech Provider as Primary v1 Channel Path *(superseded by ADR-0018)* |
| [ADR-0018](ADR-0018-meta-whatsapp-solution-partner.md) | Meta WhatsApp Solution Partner as Primary v1 Channel Path |
| [ADR-0019](ADR-0019-marketing-events-attribution.md) | Marketing Domain and Attribution Events *(Architecture Locked; Conversation feature frozen)* |
| [ADR-0020](ADR-0020-tenant-whatsapp-connection-lifecycle.md) | Tenant WhatsApp Connection Lifecycle *(Architecture Locked; Provisioning Lifecycle v1 Feature Complete / frozen)* |
| [ADR-0020 checklist](ADR-0020-lifecycle-v1-release-checklist.md) | Provisioning Lifecycle v1 release checklist *(governance closeout; companion to ADR-0020)* |
| [ADR-0021](ADR-0021-public-api-surface.md) | Public API Surface (`api.omnimsg.io`) |
| [ADR-0022](ADR-0022-ops-admin-surface.md) | Ops Admin Surface (`/admin`) |

## Template

New ADRs use the next free number and this shape:

```markdown
# ADR-00XX: Title

## Status

Proposed | Accepted | Accepted — Architecture Locked | Superseded by ADR-00YY

## Date

YYYY-MM-DD

## Platform dependencies

*(Required for capability ADRs, P4+. Omit only for pure Foundation/platform ADRs.)*

Uses:

- ADR-0020 (Lifecycle v1) — messaging-ready gate only
- message.inbound.received.v1
- Conversation / Message (platform domain models)
- Thread API / other OpenAPI contracts as needed

Does not modify:

- Lifecycle / Provisioning / ADR-0020 state machine
- Existing platform contracts (breaking changes need a new contract version)

## Context

Why a decision is needed.

## Decision

What we will do.

## Consequences

### Positive

- …

### Negative

- …

### Neutral

- …
```

File name: `ADR-00XX-short-kebab-title.md`.

Capability ADRs must follow the **Platform-first policy** in [CONTRIBUTING.md](../../CONTRIBUTING.md): integrate via API, event contracts, or documented platform models — never via another capability’s internals.