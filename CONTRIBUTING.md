# Contributing to OmniMsg

Thank you for your interest in contributing to OmniMsg. CPaaS **Foundation** (lifecycle, provisioning, inbound persistence) is complete; new work is primarily **capabilities** on stable platform contracts.

## Before You Start

- Read [docs/NORTH_STAR.md](docs/NORTH_STAR.md) for vision, architecture, and roadmap.
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

Use clear, scoped commit messages. Prefixes in use:

| Prefix | Use for |
|--------|---------|
| `foundation` | Repository skeleton, ADRs, docs, tooling setup |
| `docker` | Local dev and container definitions |
| `auth` | Gateway and API authentication |
| `messaging` | API, execution engine, providers, webhooks |
| `docs` | Governance and documentation |

Examples:

```text
foundation: add platform directory skeleton and ADRs
docker: add development compose stack
auth: validate API keys at gateway
messaging: implement WhatsApp send adapter
docs(governance): freeze Provisioning Lifecycle v1
```

## Code and Contract Guidelines

- **Contracts first** — update OpenAPI, events, or JSON Schema in `packages/contracts/` before implementation when applicable.
- **Minimize scope** — prefer small, reviewable pull requests.
- **Match conventions** — follow existing patterns in the area you are changing.
- **No secrets** — never commit credentials, API keys, or `.env` files with real values.
- **Platform-first policy** — Capability layers (P4+) must not call other capabilities’ internal implementations. Integration between capabilities goes **only** through stable platform contracts:
  - public/tenant **API** (`packages/contracts/openapi`, versioned HTTP surface),
  - **event contracts** (`packages/contracts/events/`, append-only within a version),
  - shared **domain models** that are explicitly documented as platform (e.g. `Message`, `Conversation`, messaging-ready gate).
  Do not import or invoke private worker/API helpers across capability boundaries (e.g. Agent Inbox must not call Routing internals; Marketing must not reach into worker persistence — consume `message.inbound.received.v1` instead).
- **Conversation layer is feature frozen** — do not extend `conversations` / `conversation_referrals` for marketing or attribution; implement those in the Marketing Domain ([ADR-0019](docs/adr/ADR-0019-marketing-events-attribution.md), [North Star](docs/NORTH_STAR.md#marketing--attribution-backlog)). Changes to Conversation models require a new ADR (or explicit amendment), except bug fixes.
- **WhatsApp connection lifecycle is Architecture Locked (v1 frozen)** — mutate `TenantWhatsappAccount.status` only via `omnimsg_common.whatsapp_lifecycle.transition` (or seed `bootstrap_ready`); messaging gates must use `is_messaging_ready` / `messaging_ready_statuses` ([ADR-0020](docs/adr/ADR-0020-tenant-whatsapp-connection-lifecycle.md)). CI runs `scripts/check-whatsapp-lifecycle-ssot.sh`. See the [v1 release checklist](docs/adr/ADR-0020-lifecycle-v1-release-checklist.md).
  - **Compatibility Promise:** v1 APIs, statuses, and transition rules stay compatible; incompatible changes require `lifecycle_version = 2`.
  - **Operational Freeze:** dependency is `Provisioning → Lifecycle → capabilities`. Capabilities may use lifecycle only as a read dependency (messaging-ready gate). Never mutate lifecycle from inbound / worker / gateway / capability code.
  - Capability PRs must **not** add lifecycle statuses, edit `transition` / `ALLOWED_TRANSITIONS` / `health_ok`, add provisioning endpoints, or change ADR-0020. Change Control: ADR-0020 edits need an ADR amendment (or superseding ADR).
- **Inbound quality gate** — changes to the inbound webhook pipeline must keep the regression that webhooks **without** `messages[].referral` invent **no** ConversationReferral rows (see `tests/test_conversation_referral.py`). Inbound may persist Conversation + Message.

## Pull Requests

- Link related issues.
- Note ADR or RFC implications in the PR description.
- Include a test plan, even for documentation-only changes where verification steps apply.

### Architecture Locked review rule

If a PR changes code or contracts governed by an ADR marked **Architecture Locked** (see [docs/adr/](docs/adr/), e.g. ADR-0019, ADR-0020), the PR **must** include one of:

1. a **new ADR**, or
2. an **ADR amendment**, or
3. an **explicit confirmation** in the PR description that the change is **only implementing** an already accepted decision (no new architectural choice).

Reviewers should reject silent architecture drift through code-only PRs.

**Foundation / ADR-0020:** capability PRs must **not** modify [ADR-0020](docs/adr/ADR-0020-tenant-whatsapp-connection-lifecycle.md) or the v1 lifecycle module. Needs that break Compatibility Promise go to `lifecycle_version = 2`.

## Questions

Open a GitHub issue for questions, bugs, or feature discussions.
