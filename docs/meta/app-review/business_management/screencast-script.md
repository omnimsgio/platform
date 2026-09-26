# Screencast script — App Review `business_management` (v6 · backend S2S)

**App:** OmniMsg (`3492919917530282`)  
**Business:** Finestar Hospitality (`1329905112443890`)  
**Permission:** `business_management`  
**Product:** OmniMsg / FinestAR — WhatsApp Tech Provider CPaaS  
**S2S guide:** https://developers.facebook.com/documentation/development/create-an-app/server-to-server-apps  
**Direct Support (2026-09-21):** Richard Vergiyaescu — screencast must prove backend-only (no end-user UI)

**Status 2026-09-22:** v6 package prepared per Direct Support. **v4/v5 product-UI demos are superseded** — do not upload them again.

**Recording:** `recordings/omnimsg-business-management-v6.mp4` (~52 s, 1920×1080)  
**Capture:** `recordings/record-v6.mjs`  
**Backend evidence:** System User `omnimsg_api` on `https://api.omnimsg.io` → Graph A/B/C (token never shown in full)

---

## Why v6 exists

Reject #5 had correct S2S **text**, but the screencast showed a **browser product UI** (`/app-review/business-management`). Direct Support said reviewers must see a **backend-only** integration with **no end-user-facing interface**, including how the **access token** is used.

v6 = terminal/backend only. No Discover button, no demo page URL in the submission.

---

## Meta App Dashboard — Basic Settings (S2S guide)

Manual check before Request again:

| Field | Target | Done |
|-------|--------|------|
| App icon | OmniMsg / FinestAR logo | ☐ |
| Business Use | **Client** (other businesses use OmniMsg for their WA data) | ☐ |
| Platform | **Website** → `https://omnimsg.io` | ☐ |
| Privacy Policy | `https://omnimsg.io/privacy` | ☐ |
| Live mode | Leave Live (WA already production) | ☐ |
| Business Verification | Finestar Approved | ☐ |

---

## 1. Paste — “Describe how your app uses this permission” (Add Details)

```text
OmniMsg (https://omnimsg.io) is FinestAR's WhatsApp messaging platform (Meta Tech Provider).
We already have Advanced access for whatsapp_business_messaging and whatsapp_business_management.

For business_management this app is a server-to-server integration with no end-user-facing interface
for this permission. There is no Facebook Login dialog and no permission-grant screen for
business_management. The permission is used only by our backend on https://api.omnimsg.io,
authorised by Meta Business System User omnimsg_api. The System User access token is stored only
on the server and is never sent to a browser.

Backend workflow (end-to-end):
1) After a customer completes WhatsApp Embedded Signup (or during partner ops), our server loads the
   System User access token from secure server config.
2) The server calls Graph GET /{business-id}?fields=id,name to read the Business Manager portfolio
   identity (business_management).
3) The server calls Graph GET /{business-id}/owned_whatsapp_business_accounts?fields=id,name to list
   WhatsApp Business Accounts owned by that business (business_management).
4) Optionally the server calls GET /me/businesses (informative for System User; often empty).
5) OmniMsg stores the Business ID and WABA IDs on the tenant record for onboarding and later
   credit-line attach — without asking customers to paste IDs manually.

Why business_management: it is required to read Business Manager portfolio identity and owned WABAs
via the System User so our backend can map the correct assets to a tenant and prepare credit-line
sharing. We do not use this permission to create ads, manage or claim ad accounts, build audiences,
or request advertising insights.

Platform (per Server-to-Server Apps guide): Website — https://omnimsg.io (company site; no end-user
UI for this permission). Privacy: https://omnimsg.io/privacy
```

---

## 2. Paste — Permission justification (why / where)

```text
Permission: business_management

Why needed:
- Read Business Manager portfolio identity for the partner / customer business.
- List WhatsApp Business Accounts owned by that business so OmniMsg can attach the correct WABA
  during B2B onboarding and support credit-line attach later.

Where used (server only — System User omnimsg_api on api.omnimsg.io):
- Step "Resolve business identity": GET /v21.0/{business-id}?fields=id,name
  → result written to tenant business_id / display name.
- Step "List owned WABAs": GET /v21.0/{business-id}/owned_whatsapp_business_accounts?fields=id,name
  → result used to select / store waba_id for the tenant.
- Step "Informative inventory": GET /v21.0/me/businesses?fields=id,name
  → often empty for System User; not required for onboarding.

Access token: META_BUSINESS_ACCESS_TOKEN (System User) is read from server environment on
api.omnimsg.io only. It is never exposed to browsers, mobile apps, or end users.

Not used for: ads, ad accounts, audiences, advertising insights, or consumer Facebook Login.
```

---

## 3. Paste — Testing (S2S guide: no UI test)

```text
Per Meta Server-to-Server Apps guide: there is no end-user UI for reviewers to click for this
permission. Please evaluate the attached screencast, which shows the backend using the System User
access token (redacted) and live Graph calls returning HTTP 200 for business identity and owned
WABAs. The written description above is reused here as the testing description.
```

---

## 4. Paste — Reviewer instructions / access codes

```text
This permission is server-to-server only. There is no Facebook Login and no test-user credentials.

Watch the attached screencast (backend terminal):
1) System User omnimsg_api confirmed via debug_token (token redacted on screen).
2) Server calls Graph with that token: business identity + owned WABAs (HTTP 200).
3) Captions state there is no end-user UI for business_management.

Company website (Platform): https://omnimsg.io
Privacy: https://omnimsg.io/privacy
Terms: https://omnimsg.io/terms
App ID: 3492919917530282 · Business: Finestar Hospitality (1329905112443890)
```

Facebook Login on this platform for **this permission review**: **No**.

---

## 5. Reply to Direct Support (Richard) — before or with resubmit

```text
Hi Richard,

Thank you for the clarification. We will resubmit business_management with:
1) An updated use case that states this permission is server-to-server with no end-user UI, and lists
   the backend Graph steps end-to-end.
2) A detailed why/where justification for business_management on our System User omnimsg_api.
3) A new screencast that shows only the backend: System User token usage (redacted), then live Graph
   calls for business identity and owned WABAs — no product/browser UI.

We will follow the Server-to-Server Apps guide (Platform = Website → https://omnimsg.io).

Best regards,
Ante
```

---

## 6. Pre-flight (before Record)

| Check | Done |
|-------|------|
| Prod `META_BUSINESS_ACCESS_TOKEN` present on dedicated-hel1 | ☐ |
| `debug_token` → SYSTEM_USER + `business_management` in scopes (token redacted in output) | ☐ |
| Graph B/C HTTP 200 with System User | ☐ |
| No full `EAA…` visible in recording window | ☐ |
| Target length 60–90 s, 1080p, English captions | ☐ |

---

## 7. Shot list (v6 — as recorded by `record-v6.mjs`)

| # | Caption / action |
|---|------------------|
| 1 | “OmniMsg — server-to-server; no end-user UI for business_management” |
| 2 | Terminal: debug_token → type SYSTEM_USER, user omnimsg_api, scope includes business_management (token redacted) |
| 3 | “Access token stored only on api.omnimsg.io — never sent to a browser” |
| 4 | curl GET business id → Finestar Hospitality HTTP 200 |
| 5 | curl owned WABAs → HTTP 200 |
| 6 | curl /me/businesses → data [] informative |
| 7 | “Same calls used in production backend for WABA mapping / credit-line prep” |
| 8 | “No Facebook Login / grant screen — System User S2S only” |

### Do **not** include

- Product demo at `/app-review/business-management`
- Discover Business Assets button / browser UI
- Graph API Explorer
- User Token / OAuth / grant dialog
- Full access tokens

---

## 8. Export & upload

| Item | Value |
|------|-------|
| File | `recordings/omnimsg-business-management-v6.mp4` |
| Also copy to | `C:\Users\avrca\Downloads\omnimsg-business-management-v6.mp4` |
| Upload | App Review → business_management screencast field **only** (replace v4) |

Submit only after a human confirms the video shows System User + redacted token usage + B/C 200 with **no** product UI.
