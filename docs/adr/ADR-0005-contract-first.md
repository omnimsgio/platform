# ADR-0005: Contract-First Architecture

## Status

Accepted

## Date

2026-07-13

## Context

OmniMsg spans HTTP APIs, async events, validation schemas, and multiple client SDKs. If implementations define interfaces ad hoc, documentation, clients, and services will drift apart.

## Decision

**Contracts are the source of truth.** Implementation follows contracts, not the reverse.

Contract artifacts live in `packages/contracts/`:

- `openapi/` — public HTTP API specification
- `events/` — async event payloads and versioning
- `jsonschema/` — shared validation schemas
- `protobuf/` — optional binary/event interchange formats
- `examples/` — canonical request/response and event examples for generators and tests

Rules:

- API handlers, gateway routing, worker consumers, and SDKs must conform to published contracts.
- Contract changes are reviewed for backward compatibility per the versioning strategy (ADR-0010).
- Contract tests in `packages/testing/contracts/` validate implementations against published artifacts.

## Consequences

### Positive

- Single source of truth for API, events, and validation.
- SDK generation and contract testing become first-class workflows.
- Cross-team changes are explicit and reviewable at the contract layer.

### Negative

- Contract updates add ceremony compared to code-only changes.
- Teams must maintain discipline to avoid "implementation-first" shortcuts.

### Neutral

- Not all internal service-to-service calls require public OpenAPI exposure; internal contracts may live alongside public ones with clear scope.
