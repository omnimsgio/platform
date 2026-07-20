# ADR-0011: Observability

## Status

Accepted

## Date

2026-07-13

## Context

OmniMsg orchestrates multi-step, multi-provider message flows. Without metrics, distributed tracing, and structured logging from the start, incidents will be slow to diagnose and performance regressions hard to detect.

## Decision

OmniMsg will implement **observability from day one**, using **OpenTelemetry-compatible** instrumentation where practical.

Observability scope includes:

- **Metrics** — request rates, latency, error rates, queue depth, provider success/failure ratios
- **Tracing** — end-to-end traces across gateway, API, worker, and provider calls
- **Logging** — structured JSON logs with correlation IDs and tenant context (without leaking secrets)
- **Profiling** — supported in staging and production troubleshooting workflows

Infrastructure assets for dashboards, collectors, and alerting live under `infrastructure/observability/`.

All services (`apps/gateway`, `apps/api`, `apps/worker`) emit telemetry through shared conventions defined in `packages/common/` as implementations mature.

## Consequences

### Positive

- Faster incident response and clearer SLO tracking.
- Provider degradation and retry storms become visible early.
- OpenTelemetry alignment avoids vendor lock-in for telemetry backends.

### Negative

- Instrumentation and collector infrastructure add upfront work.
- Log volume and trace storage require cost and retention policies.

### Neutral

- Specific vendors (Grafana, Datadog, Cloudflare observability, etc.) are implementation choices documented in infrastructure, not fixed by this ADR.
