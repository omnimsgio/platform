# ADR-0003: API-First Design

## Status

Accepted

## Date

2026-07-13

## Context

OmniMsg must serve diverse clients: backend services, automation pipelines, partner integrations, and eventually a customer portal. If each surface invents its own integration path, behavior will diverge and the platform will be harder to test, document, and evolve.

## Decision

The **public HTTP API** is the primary and authoritative integration interface for OmniMsg.

- All customer-facing capabilities are exposed through versioned REST endpoints (starting with `/v1/`).
- The portal (`apps/portal/`) is a consumer of the same API, not a parallel integration path.
- SDKs (`packages/sdk-python`, `packages/sdk-js`, `packages/sdk-go`) are generated or maintained to mirror the public API contracts.
- Internal services (worker, gateway) integrate through defined contracts and service boundaries, but external consumers use the public API surface.

## Consequences

### Positive

- One contract to document, version, test, and support.
- Portal and SDK features inherit API guarantees and backward-compatibility rules.
- Contract-first development becomes practical because the API spec leads implementation.

### Negative

- Some portal or admin workflows may require API endpoints that are not needed by typical API consumers.
- API design must balance generality with operational/admin use cases.

### Neutral

- Webhooks and async events complement the API but do not replace it as the primary command interface.
