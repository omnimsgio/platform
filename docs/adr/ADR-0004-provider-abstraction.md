# ADR-0004: Provider Abstraction and Execution Engine

## Status

Accepted

## Date

2026-07-13

## Context

Messaging providers differ in authentication, payload formats, rate limits, delivery semantics, and error models. A naive `API → Provider` design couples the public interface to vendor specifics and makes provider changes risky.

OmniMsg requires a model where the public API remains stable while provider integrations evolve independently.

## Decision

OmniMsg will implement an **Execution Engine pattern** with **Provider Adapters**:

```text
API (business logic, stable public interface)
  ↓
Execution Engine (orchestration, routing, retries, state)
  ↓
Provider Adapter (channel-specific abstraction)
  ↓
Vendor (Meta / Twilio / Infobip / ...)
```

Key rules:

- `apps/api` contains business logic and exposes the stable public interface.
- The execution engine handles orchestration, routing, retries, and execution state.
- Provider adapters live under `packages/providers/` organized by channel (whatsapp, sms, email, rcs, push).
- New vendors are added as adapter implementations without changing public API contracts.
- The gateway (`apps/gateway/`) remains separate from business logic and handles edge concerns only.

## Consequences

### Positive

- Vendor swaps and multi-vendor routing do not require customer code changes.
- Channel-specific logic is isolated and testable in adapter packages.
- Retries, failover, and degradation policies are centralized in the execution engine.

### Negative

- Additional internal layers increase initial implementation complexity.
- Adapter maintenance is ongoing as vendors change APIs and capabilities.

### Neutral

- Vendor-specific subdirectories (e.g. `packages/providers/whatsapp/meta/`) may be introduced as implementations mature.
