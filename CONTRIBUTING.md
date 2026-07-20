# Contributing to OmniMsg

Thank you for your interest in contributing to OmniMsg. This document outlines how to get involved while the platform is in early development.

## Before You Start

- Read [docs/NORTH_STAR.md](docs/NORTH_STAR.md) for vision, architecture, and v1 scope.
- Review relevant [Architecture Decision Records](docs/adr/) before proposing structural changes.
- For proposals not yet accepted as ADRs, use [docs/rfcs/](docs/rfcs/).

## How to Contribute

1. Open an issue to discuss significant changes before opening a pull request.
2. Fork the repository and create a branch from `main`.
3. Make focused changes that align with contract-first and execution engine principles.
4. Open a pull request using the PR template and describe your test plan.
5. Ensure CI passes (`.github/workflows/ci.yml`: Ruff, pytest, OpenAPI presence).

## Branch Strategy

- `main` — stable integration branch.
- Feature branches — short-lived branches for individual changes.
- Use descriptive branch names (e.g. `feat/gateway-api-key-auth`, `docs/adr-provider-failover`).

## Commit Conventions

Use clear, scoped commit messages. Prefixes in use during foundation:

| Prefix | Use for |
|--------|---------|
| `foundation` | Repository skeleton, ADRs, docs, tooling setup |
| `docker` | Local dev and container definitions |
| `auth` | Gateway and API authentication |
| `messaging` | API, execution engine, providers, webhooks |

Examples:

```text
foundation: add platform directory skeleton and ADRs
docker: add development compose stack
auth: validate API keys at gateway
messaging: implement WhatsApp send adapter
```

## Code and Contract Guidelines

- **Contracts first** — update OpenAPI, events, or JSON Schema in `packages/contracts/` before implementation when applicable.
- **Minimize scope** — prefer small, reviewable pull requests.
- **Match conventions** — follow existing patterns in the area you are changing.
- **No secrets** — never commit credentials, API keys, or `.env` files with real values.

## Pull Requests

- Link related issues.
- Note ADR or RFC implications in the PR description.
- Include a test plan, even for documentation-only changes where verification steps apply.

## Questions

Open a GitHub issue for questions, bugs, or feature discussions.
