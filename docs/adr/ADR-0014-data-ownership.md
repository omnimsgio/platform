# ADR-0014: Data Ownership

## Status

Accepted

## Date

2026-07-13

## Context

OmniMsg stores message metadata, delivery events, tenant configuration, and webhook payloads. Customers and regulators expect clear data boundaries, retention rules, and privacy compliance—especially in a multi-tenant SaaS model.

## Decision

OmniMsg adopts explicit **data ownership** and **isolation** rules:

### Tenant Isolation

- All tenant-owned data is scoped by tenant identifier.
- Queries, exports, and deletes operate within tenant boundaries only.

### Message Ownership

- Customers own the content and metadata of messages they send through the platform.
- The platform processes and stores data as a processor according to published policies.

### Retention

- Retention policies are configurable within platform-defined bounds.
- Expired data is purged or anonymized per documented schedules in `docs/security/`.

### Compliance

- GDPR-oriented requirements (access, deletion, data minimization) inform schema and API design.
- Cross-border data handling is documented per deployment region as infrastructure choices solidify.

## Consequences

### Positive

- Trustworthy multi-tenant data model for enterprise customers.
- Clear basis for data export and deletion APIs.
- Compliance discussions are anchored in documented ownership rules.

### Negative

- Retention and deletion workflows add storage and indexing complexity.
- Regional deployment may be required for some customers.

### Neutral

- Legal agreements (DPA, terms) complement but do not replace technical isolation enforced by the platform.
