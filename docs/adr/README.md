# Architecture Decision Records

Accepted decisions that shape OmniMsg. Propose changes via [RFCs](../rfcs/) when an ADR is not yet appropriate.

Product context: [omnimsg.io](https://omnimsg.io) · [FinestAR](https://finestar.hr/) · [North Star](../NORTH_STAR.md)

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

## Template

New ADRs use the next free number and this shape:

```markdown
# ADR-00XX: Title

## Status

Proposed | Accepted | Superseded by ADR-00YY

## Date

YYYY-MM-DD

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
