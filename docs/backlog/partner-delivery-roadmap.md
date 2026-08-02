# Partner delivery roadmap (post–SQLAdmin v1)

SQLAdmin v1 is **frozen** (`cpaas-sqladmin-v1`). Engineering focus shifts to CPaaS capability for first external tenants.

## Priority sequence

| Priority | Goal | GO criterion |
|----------|------|--------------|
| 1 | **Embedded Signup / onboarding** | Tenant can connect a WABA without manual ops intervention |
| 2 | **Messaging API stabilisation** | Public `/v1` API is treated as stable enough for first partners |
| 3 | **Webhook lifecycle** | Reliable handling of Meta events + recovery paths |
| 4 | **SDK generation** | TypeScript → Python → Go from the OpenAPI contract |
| 5 | **Partner documentation** | An external developer can onboard using docs alone |
| 6 | **First external tenant** | End-to-end onboarding + send without developer assistance |

## Gate: API Freeze (before SDK generation)

Before starting priority **4 (SDK generation)**, declare a short **API Freeze** for the first partner-facing surface. Freeze does **not** stop all product work; it means the following are treated as stable for SDK v1:

- Public `/v1` endpoints (paths + methods)
- Request / response models
- Error envelope (ADR-0015)
- Authentication model (Bearer API key)

After freeze: contract changes that break generated clients require an explicit version bump / migration note. Prefer finishing priorities 1–3 enough that the public surface is not churning weekly.

## Out of scope here

- SQLAdmin v2 — see [sqladmin-v2.md](sqladmin-v2.md)
- Expanding frozen Lifecycle v1 / Conversation marketing surface without a new ADR
