# ADR-0010: Versioning Strategy

## Status

Accepted

## Date

2026-07-13

## Context

OmniMsg will evolve its HTTP API, event schemas, and client SDKs while customers depend on stable integrations. Without explicit versioning rules, breaking changes will fragment the ecosystem and erode trust.

## Decision

OmniMsg adopts the following versioning model:

### HTTP API

- Public endpoints are prefixed with a major version path (e.g. `/v1/`).
- Breaking changes require a new major API version.
- Non-breaking additions (new optional fields, new endpoints) are allowed within the same major version.

### Contracts

- OpenAPI, event, and JSON Schema changes follow semantic intent: backward-compatible edits vs breaking revisions.
- Breaking contract changes are paired with version bumps and migration notes.

### SDKs

- SDKs use **semantic versioning** aligned with generated or published API client packages.
- SDK major versions map to API major versions where applicable.

### Deprecation

- Deprecated fields and endpoints are documented, announced, and removed only after a defined sunset period.

## Consequences

### Positive

- Predictable upgrade path for API consumers and SDK users.
- Contract review gates catch accidental breaking changes early.

### Negative

- Maintaining multiple API major versions increases long-term support cost.
- Event schema evolution requires disciplined compatibility testing.

### Neutral

- Internal service contracts may version independently but should still avoid unnecessary breaking churn.
