# ADR-0012: Security Model

## Status

Accepted

## Date

2026-07-13

## Context

OmniMsg handles API credentials, tenant data, provider secrets, and inbound webhooks from external systems. A fragmented security approach across gateway, API, and workers would create gaps exploitable in authentication, webhook verification, or secret handling.

## Decision

OmniMsg will implement a layered **security model**:

### Edge and API Access

- **API keys** for programmatic access, validated at `apps/gateway/`.
- **OAuth** and **JWT** support for user-facing and service-to-service scenarios as the portal and internal auth mature.

### Webhooks

- Inbound provider webhooks are verified using provider-specific **signatures** before normalization into internal events.
- Outbound customer webhooks are signed by the platform; customers verify authenticity.

### Data Protection

- Secrets and provider credentials are encrypted at rest and never logged.
- TLS is required for all external and inter-service communication in non-local environments.

### Secrets Management

- Secrets are injected via environment or platform secret stores (ADR-0009).
- Repository commits must not contain credentials; security review applies to infrastructure templates.

Security documentation and disclosure process are maintained in `docs/security/` and `SECURITY.md`.

## Consequences

### Positive

- Defense in depth from gateway through worker processing.
- Clear expectations for webhook authenticity and tenant isolation.
- Responsible disclosure path for external researchers.

### Negative

- Multiple auth mechanisms increase implementation and documentation surface.
- Key rotation and signature algorithm upgrades require operational runbooks.

### Neutral

- Fine-grained RBAC for portal users will be specified as the portal matures.
