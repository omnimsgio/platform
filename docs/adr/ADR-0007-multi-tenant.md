# ADR-0007: Multi-Tenant by Default

## Status

Accepted

## Date

2026-07-13

## Context

OmniMsg is intended to serve multiple customers from a shared platform. Retrofitting tenancy later typically forces painful data migrations, authorization rewrites, and configuration model changes.

## Decision

OmniMsg will be **multi-tenant from the start**.

Tenancy boundaries apply to:

- **Authentication** — API keys and credentials are scoped to a tenant.
- **Data** — messages, templates, webhook subscriptions, and audit data are tenant-isolated.
- **Configuration** — provider credentials, routing rules, and feature flags are per-tenant.

Every request processed by the gateway and API must resolve a tenant context before executing business logic. Cross-tenant data access is prohibited by design.

## Consequences

### Positive

- SaaS-ready architecture without a later "tenancy retrofit" project.
- Clear isolation model for security reviews and compliance.
- Per-tenant provider configuration supports BYO-credentials models.

### Negative

- All schemas, queries, and caches must carry tenant context.
- Testing and local development require explicit tenant fixtures.

### Neutral

- Deployment topology (shared vs dedicated infrastructure per tenant) is a separate operational decision not fixed by this ADR.
