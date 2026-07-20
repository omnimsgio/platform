# ADR-0001: Platform Vision

## Status

Accepted

## Date

2026-07-13

## Context

Organizations need to send messages across multiple channels (WhatsApp, SMS, email, RCS, push) and often integrate with different providers (Meta, Twilio, Infobip, and others). Building and maintaining separate integrations per channel and per provider is costly, inconsistent, and slows product delivery.

OmniMsg is being built to solve this fragmentation by offering a single, unified messaging platform.

## Decision

OmniMsg will be an **API-first omnichannel messaging platform** with the guiding principle:

> One API. Any channel. Any provider.

The platform will:

- Expose a stable, versioned HTTP API as the primary integration surface.
- Abstract channel and provider differences behind a consistent execution model.
- Support multiple messaging channels through provider adapters.
- Enable tenants to route messages to their preferred providers without changing client code.

## Consequences

### Positive

- Clear product identity and north-star alignment across teams and documentation.
- Customers integrate once and gain access to multiple channels over time.
- Provider additions become platform capabilities rather than customer migration projects.

### Negative

- The platform must invest early in abstraction layers (execution engine, contracts, adapters).
- Uniform API ergonomics must coexist with real channel/provider capability differences.

### Neutral

- Portal, SDKs, and operational tooling are secondary surfaces built on top of the API vision.
