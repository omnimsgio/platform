# ADR-0008: Provider Capability Model

## Status

Accepted

## Date

2026-07-13

## Context

Messaging channels are not uniform. WhatsApp supports templates and session windows; SMS has segment limits; email supports rich HTML; RCS and push have distinct feature sets. Pretending all channels behave identically leads to broken integrations and false API promises.

## Decision

Providers and channels will declare **capabilities** explicitly. The public API will not assume feature parity across channels.

Capability examples include:

- Supported message types (text, media, template, interactive)
- Delivery receipts and read receipts
- Scheduling and batching
- Template management
- Rate limits and throughput tiers
- Geographic or regulatory constraints

Rules:

- Adapters in `packages/providers/` register capabilities for each provider implementation.
- The execution engine routes requests only to providers that declare required capabilities.
- API responses surface capability gaps with structured errors (see ADR-0015) rather than opaque failures.
- Documentation in `docs/providers/` describes channel-specific behavior and limits.

## Consequences

### Positive

- Honest API design aligned with real provider behavior.
- Clients can introspect or document channel limits programmatically over time.
- New providers integrate without forcing unsupported features.

### Negative

- Client integrations must handle channel-specific branches or capability checks.
- Capability metadata must be maintained as vendors evolve.

### Neutral

- Uniform request shapes may still exist where they add value; uniformity is not assumed for behavior.
