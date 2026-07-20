# ADR-0006: Event-Driven Architecture

## Status

Accepted

## Date

2026-07-13

## Context

Messaging workflows are inherently asynchronous: send requests are accepted quickly, delivery happens later, webhooks arrive from providers, and retries may span minutes or hours. Synchronous-only processing would block API requests, complicate scaling, and make failure recovery brittle.

## Decision

OmniMsg will use an **event-driven architecture** for asynchronous flows.

- Event contracts are defined in `packages/contracts/events/` and are versioned alongside the HTTP API.
- `apps/worker` consumes and publishes platform events for delivery, retries, webhook processing, and downstream notifications.
- The API accepts commands and emits events; workers perform long-running or provider-bound work.
- Webhook ingress is normalized into internal events before business logic processes them.

Event naming, schemas, and compatibility rules follow the contract-first model (ADR-0005).

## Consequences

### Positive

- API latency stays low; heavy work moves off the request path.
- Retries, backoff, and dead-letter handling are natural worker concerns.
- New async capabilities can be added without changing synchronous API shapes when possible.

### Negative

- Distributed flows require idempotency, ordering, and observability investment.
- Debugging spans multiple services and event traces.

### Neutral

- Not every operation must be async; read-heavy or simple operations may remain synchronous where appropriate.
