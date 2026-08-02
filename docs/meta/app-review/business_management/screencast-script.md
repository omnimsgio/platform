# Screencast script — App Review `business_management`

**App:** OmniMsg (`3492919917530282`)  
**Business:** Finestar Hospitality (`1329905112443890`)  
**Permission:** `business_management`  
**Product:** OmniMsg / FinestAR — WhatsApp Solution Partner CPaaS ([omnimsg.io](https://omnimsg.io))

Meta requires a **written description** + **screencast** of end-to-end use. Record in English (or subtitle). Do **not** show access tokens, app secrets, or `.env`.

Related: [notes.md](notes.md), [graph-response.json](graph-response.json).

---

## 1. Paste into App Review — “Describe how your app uses this permission”

```text
OmniMsg (omnimsg.io) is a WhatsApp Solution Partner platform operated by FinestAR. We request business_management so that an authorized app admin can discover and verify Meta Business assets required for WhatsApp Business onboarding and operations.

Specifically, with a user who administers the business portfolio, OmniMsg calls the Business Manager / Graph API to:
1) list businesses the admin can access (GET /me/businesses),
2) read business identity fields (GET /{business-id}?fields=id,name),
3) list WhatsApp Business Accounts owned by that business (GET /{business-id}/owned_whatsapp_business_accounts).

This is necessary so OmniMsg can map the correct Business ID and WABA to a tenant during Solution Partner onboarding and support, without asking customers to paste IDs manually. The permission is used only to read/manage business assets the app user already administers. We do not use this permission to create ads, manage ad accounts, build audiences, or request advertising insights.
```

---

## 2. Pre-flight (before Record)

| Check | Done |
|-------|------|
| Graph API Explorer: Meta App = **OmniMsg** | ☐ |
| Token type = **User Token** (Ante / admin on Finestar Hospitality) | ☐ |
| Permission `business_management` checked when generating token | ☐ |
| Browser zoom readable; hide bookmarks bar if noisy | ☐ |
| Close tabs with secrets / `.env` / token strings | ☐ |
| Optional: open [omnimsg.io](https://omnimsg.io) and portal briefly for product context | ☐ |
| Target length: **60–120 seconds** | ☐ |

Call paths to show (HTTP 200):

1. `GET /v21.0/me/businesses?fields=id,name`
2. `GET /v21.0/1329905112443890?fields=id,name`
3. `GET /v21.0/1329905112443890/owned_whatsapp_business_accounts?fields=id,name`

---

## 3. Shot list (record this order)

### Shot A — Product context (10–15s)

1. Open **https://omnimsg.io** (or portal Connect WhatsApp if feature flag on).
2. Voiceover: *“OmniMsg is FinestAR’s WhatsApp Solution Partner messaging platform. Customers connect a WhatsApp Business Account through our portal.”*

### Shot B — Who uses the permission (10s)

1. Show Meta **Business Settings** → portfolio **Finestar Hospitality** (no need to open System users if it confuses reviewers).
2. Or stay in Graph API Explorer and say: *“An OmniMsg admin who already administers the Finestar Hospitality business portfolio uses business_management so our backend can discover businesses and WABAs.”*

### Shot C — Graph API Explorer setup (15s)

1. Open [Graph API Explorer](https://developers.facebook.com/tools/explorer/).
2. Meta App: **OmniMsg**.
3. User or Page: **User Token** (do not scroll the token into view; blur or crop if needed).
4. Show Permissions panel briefly with **`business_management`** visible (other WA scopes OK).

### Shot D — End-to-end API use (40–60s) — **core of the review**

Run each call; pause so JSON is readable:

**D1.** Path: `me/businesses?fields=id,name` → **Submit**  
- Point at returned businesses (e.g. Finestar Hospitality, Fine Star, stay.hr).  
- VO: *“We list businesses the admin can access.”*

**D2.** Path: `1329905112443890?fields=id,name` → **Submit**  
- VO: *“We read the business identity for the partner portfolio.”*

**D3.** Path: `1329905112443890/owned_whatsapp_business_accounts?fields=id,name` → **Submit**  
- Point at WABA names (Test WABA, Finestar Hospitality, stay_hr, etc.).  
- VO: *“We list WhatsApp Business Accounts owned by that business so OmniMsg can attach the correct WABA during onboarding — without ad account or ads insights APIs.”*

### Shot E — Close (5–10s)

1. Optional: briefly show OmniMsg portal “Connect WhatsApp” (ES) as the product surface that needs those IDs.  
2. VO: *“business_management is only used for Business Manager asset discovery for WhatsApp onboarding and operations.”*

---

## 4. Full voiceover (optional — read as one take)

```text
OmniMsg is a WhatsApp Solution Partner platform by FinestAR. We request the business_management permission so an admin who already manages our Meta business portfolio can discover Business Manager assets needed for WhatsApp onboarding.

In Graph API Explorer, with the OmniMsg app and a user token that includes business_management, we call me/businesses to list accessible businesses.

Next we read business 1329905112443890 — Finestar Hospitality — to confirm identity.

Finally we list owned WhatsApp Business Accounts for that business. OmniMsg uses these IDs to map the correct WABA to a tenant. We do not use this permission for ads, ad accounts, audiences, or advertising insights.
```

---

## 5. Export & upload

| Item | Recommendation |
|------|----------------|
| Format | MP4 or MOV |
| Resolution | 1080p if possible |
| Audio | Mic OK; English preferred |
| Privacy | Blur token field if it appears |
| Upload | App Review → Allowed usage → `business_management` → Upload screencast |

Also tick: *If approved, I agree … allowed usage.*  
**Save** draft. Submit only when Testing use cases shows `business_management` **1 of 1 / Completed**.

---

## 6. What reviewers should *not* see

- Full `EAAG…` / `EAA…` access tokens  
- `META_APP_SECRET` / `.env`  
- Unrelated ads Manager UI (would confuse allowed usage)
