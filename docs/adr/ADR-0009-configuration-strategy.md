# ADR-0009: Configuration Strategy

## Status

Accepted

## Date

2026-07-13

## Context

OmniMsg runs across multiple environments (local, staging, production) and must store sensitive provider credentials per tenant. Configuration approaches that mix secrets with application code or rely on implicit globals create security and operability risks.

## Decision

OmniMsg will use **environment-based configuration** with **secret management** for sensitive values.

Principles:

- Non-secret settings (service URLs, feature flags, log levels) are supplied via environment variables or environment-specific config files checked into appropriate infrastructure paths.
- Secrets (API keys, provider tokens, signing keys) are never committed to the repository.
- Provider credentials are stored and resolved **per tenant**, not as global platform defaults, except for platform-owned sandbox credentials in non-production environments.
- Configuration is validated at service startup; missing or invalid config fails fast.

Infrastructure-specific secret storage (e.g. Cloudflare, Hetzner, Kubernetes secrets) will be defined in `infrastructure/` as the deployment model matures.

## Consequences

### Positive

- Clear separation between code, config, and secrets.
- Per-tenant credential model aligns with multi-tenancy (ADR-0007).
- Environment parity is easier to reason about and document.

### Negative

- Local development requires documented secret setup or test doubles.
- Rotating credentials requires operational procedures per tenant and provider.

### Neutral

- A future centralized configuration service may complement but not replace secret management requirements.
