# ADR-0015: Error Model

## Status

Accepted

## Date

2026-07-13

## Context

Provider APIs return disparate error formats, status codes, and retry hints. If OmniMsg surfaces raw provider errors, clients cannot build reliable automation. If each endpoint invents its own error shape, SDKs and documentation fragment.

## Decision

OmniMsg will expose a **uniform error format** across the public API.

Principles:

- All API errors use a consistent JSON structure with stable platform **error codes**.
- HTTP status codes reflect error class (validation, auth, not found, conflict, rate limit, upstream failure).
- Provider-specific errors are **mapped** to platform codes; raw vendor payloads are not exposed by default.
- Errors include correlation identifiers for support and observability (ADR-0011).
- Retryability is indicated explicitly where relevant (e.g. `retryable: true` for transient upstream failures).

Provider mapping tables and code definitions will live alongside contracts and provider documentation. Event processing failures use analogous normalized error metadata in event payloads.

## Consequences

### Positive

- Predictable client error handling across channels and providers.
- SDKs can expose typed errors aligned with platform codes.
- Support teams diagnose issues using stable codes and trace IDs.

### Negative

- Adapter layer must maintain mapping tables as vendors change error semantics.
- Some vendor-specific nuance is intentionally hidden unless exposed via optional debug fields in non-production environments.

### Neutral

- Webhook delivery status events may carry both platform codes and summarized provider context for auditing.
