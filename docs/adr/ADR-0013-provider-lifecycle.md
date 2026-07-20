# ADR-0013: Provider Lifecycle

## Status

Accepted

## Date

2026-07-13

## Context

Providers are onboarded, monitored, degraded, replaced, and eventually deprecated. Without explicit lifecycle management, routing logic becomes ad hoc and outages propagate silently to customers.

## Decision

OmniMsg will manage providers through a defined **lifecycle**:

1. **Registration** — adapters register metadata, capabilities (ADR-0008), and health check endpoints or probes.
2. **Health checks** — periodic or on-demand checks determine provider availability.
3. **Degradation** — partial failures reduce traffic or mark providers unhealthy without immediate hard failure where alternatives exist.
4. **Failover** — execution engine routes to fallback providers based on tenant configuration and capability match.
5. **Deprecation** — providers are marked deprecated with documented sunset timelines; new sends are blocked after cutoff.

Lifecycle state is observable via metrics and logs (ADR-0011) and documented per provider in `docs/providers/`.

## Consequences

### Positive

- Predictable behavior during provider outages.
- Safer vendor migrations with explicit deprecation windows.
- Operations teams gain visibility into provider health.

### Negative

- Failover configuration adds tenant-level complexity.
- Health check accuracy varies by vendor and must be maintained per adapter.

### Neutral

- Automatic failover is not guaranteed for all channels in v1; behavior will be documented per release.
