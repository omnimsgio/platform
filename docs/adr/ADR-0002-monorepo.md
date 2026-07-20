# ADR-0002: Monorepo Structure

## Status

Accepted

## Date

2026-07-13

## Context

OmniMsg spans multiple deployable applications (gateway, API, worker, portal), shared libraries (contracts, providers, SDKs), infrastructure definitions, and documentation. Splitting these into separate repositories early would increase coordination overhead without delivering immediate value at the foundation stage.

## Decision

OmniMsg will use a **single monorepo** with the following top-level layout:

- `apps/` — deployable services (gateway, api, worker, portal)
- `packages/` — shared libraries (contracts, providers, SDKs, testing utilities)
- `infrastructure/` — cloud, observability, and deployment assets
- `docker/` — local and production container definitions
- `docs/` — architecture, ADRs, RFCs, and operational documentation
- `scripts/` — repository automation and developer tooling

Applications and packages will remain in this structure without premature reorganization into separate repositories.

## Consequences

### Positive

- Atomic changes across API contracts, implementations, and infrastructure.
- Simpler onboarding: one clone, one issue tracker, one CI context.
- Shared tooling and conventions apply consistently across components.

### Negative

- Repository size and CI scope grow over time and require disciplined boundaries.
- Access control is coarser than per-service repositories unless supplemented with CODEOWNERS and path-based policies.

### Neutral

- Future extraction of a package or service into its own repository remains possible if operational needs justify it.
