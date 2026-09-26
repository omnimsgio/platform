# App Review evidence — `business_management`

**Phase:** 1 (Meta Dashboard — permission + token + test call + App Review)  
**Product:** OmniMsg / FinestAR  
**Kickoff tracker:** `/opt/stacks/ops/omnimsgio-meta-sp-kickoff.md`  
**Runbook:** `docs/providers/meta-whatsapp-solution-partner.md`  
**Screencast (v6 backend S2S):** [screencast-script.md](screencast-script.md)  
**Direct Support reply draft:** [reply-to-richard-direct-support.txt](reply-to-richard-direct-support.txt)

## Identifiers

| Field | Value |
|-------|--------|
| Graph API version | `v21.0` |
| App ID | `3492919917530282` (OmniMsg) |
| Business ID | `1329905112443890` (Finestar Hospitality) |
| System User | `omnimsg_api` (`122113353693380836`) |
| Backend host | `https://api.omnimsg.io` (System User token only here) |
| Deployed SHA (`dedicated-hel1`) | `971ed150a11f2a330b3489487db31c483cca2ebc` (`main`, PR #6 squash) |
| Merged PR | https://github.com/omnimsgio/platform/pull/6 |

Internal demo (not for v6 submission): https://omnimsg.io/app-review/business-management · `POST /app-review/bm-discover`

---

## Current status (2026-09-22) — v6 package READY (await human GO)

| Item | Status |
|------|--------|
| `business_management` Advanced Review | **Rejected ×5** — **v6 ready** per Direct Support (Richard Vergiyaescu) |
| Direct Support | 2026-09-21/22: screencast must prove **backend-only / no end-user UI** + how access token is used |
| v6 screencast | **Recorded** — `recordings/omnimsg-business-management-v6.mp4` (~52 s); also Windows Downloads |
| v6 submission copy | [screencast-script.md](screencast-script.md) §§1–4 |
| Product-UI demos (v3–v5) | **Superseded** — do not upload again |
| Next step | Dashboard checklist → paste Richard reply → Request again **after** human GO on v6 video |

**Residual risk:** Meta allowed usage for BM remains ad-account centric. v6 satisfies Direct Support; approval still not guaranteed.

---

## Meta App Dashboard — Basic Settings (S2S guide) — manual

Per https://developers.facebook.com/documentation/development/create-an-app/server-to-server-apps — verify before Request again:

| Field | Target | Done |
|-------|--------|------|
| App icon | OmniMsg / FinestAR logo | ☐ |
| Business Use | **Client** | ☐ |
| Platform | **Website** → `https://omnimsg.io` | ☐ |
| Privacy Policy | `https://omnimsg.io/privacy` | ☐ |
| Live mode | Leave Live (WA production) | ☐ |
| Business Verification | Finestar Approved | ☐ |

Do not turn Live off or remove Website — WA/ES depend on them. S2S framing applies to this **permission submission**.

---

## Direct Support (2026-09-21/22) — Richard Vergiyaescu

Written S2S description was OK; screencast did **not** show backend-only / no end-user UI. Next package must include backend steps, why/where for the permission, and a screencast showing token usage (System User) aligned to that use case.

Draft follow-up: [reply-to-richard-direct-support.txt](reply-to-richard-direct-support.txt)

---

## v6 evidence (2026-09-22)

| Check | Result |
|-------|--------|
| `debug_token` type | `SYSTEM_USER` |
| User | `omnimsg_api` |
| `business_management` in scopes | **Yes** |
| Call B | HTTP 200 Finestar Hospitality |
| Call C | HTTP 200 (3 WABAs) |
| Call A | HTTP 200 `data: []` |
| Video | terminal + captions; token `EAA…[REDACTED]`; **no** product UI |

Reproduce: `node recordings/record-v6.mjs` (SSH to dedicated-hel1 + Playwright + ffmpeg).

---

## Submit gate (do not Request again until all true)

1. ☐ Dashboard Basic Settings checklist above  
2. ☐ Paste Describe + justification + Testing from screencast-script.md v6 (**no** demo URL)  
3. ☐ Upload **v6** MP4 only  
4. ☐ Remove old supporting videos if still attached  
5. ☐ Reviewer instructions / access codes = v6 paste; Facebook Login = **No** for this permission  
6. ☐ Human watched v6 (System User + B/C 200, no browser demo)  
7. ☐ Optional: send reply-to-richard-direct-support.txt in Direct Support  

Then **Request again**.

---

## Reject #5 (2026-09-17) — correct S2S text, product-UI screencast

Unlike reject #4, Permission usage **did** declare server-to-server / System User. Feedback was still Policy 1.6 boilerplate. Direct Support later clarified the gap: the **screencast showed a UI**, so reviewers did not treat it as backend-only S2S.

---

## Reject #4 (2026-09-15 ~05:07) — same feedback, form still had v1 text

Feedback was the identical Policy 1.6 template. The Permission usage text for that attempt still began with the v1 user-admin wording, so feedback item 5 (declare S2S) was not invoked.

## Submission 2026-09-15 08:52 — v5 package (rejected 2026-09-17)

- Permission usage: S2S + System User `omnimsg_api`
- Screencast: v4 **product UI** (superseded by v6)
- WA messaging + management Renewed

---

## Why Advanced BM is not on the critical path (2026-09-07)

Meta docs contradict the assumption that this permission blocks us:

| Finding | Source / consequence |
|---------|----------------------|
| Tech Provider requires **only** `whatsapp_business_messaging` + `whatsapp_business_management` Advanced | Both already **Renewed** — BM is not on the required list |
| `GET /{business-id}/owned_whatsapp_business_accounts` is documented under **`whatsapp_business_management`** | Our screencast Call C therefore does not demonstrate a need for BM |
| BM allowed usage is ad-account centric (manage/claim ad accounts, aggregated analytics insights) | Our WhatsApp/WABA discovery narrative sits outside the documented allowed usage — no screencast fixes that mismatch |
| Credit-line sharing requires BM **granted to the app in the system user token** + Admin/Finance Editor role | Both already satisfied; Advanced access is not stated as a requirement |
| Extended Credit Line | **Not provisioned** — Phase 2 is blocked on SP status regardless |

Practical read: Standard access plus BM in the System User token already covers everything we run today. Treat a v4 submission as optional upside, not a dependency, and stop iterating if it is rejected again.

---

## Rejection history

| Date | Submitted | Issue |
|------|-----------|-------|
| ~2026-08-03 | v1 | No login/grant, Explorer/paste token, no E2E in product |
| ~2026-08-26 | v2 | Graph Explorer + OAuth-style grant; not aligned with server-to-server use case |
| 2026-09-05 (result 2026-08-27 form) | v3 | Screencast was correct S2S, but **submission text was still the v1 user-admin copy** |
| **2026-09-15** | labelled “v4” attempt | Same Policy 1.6 template; **Permission usage text still v1 user-admin copy** — S2S waiver (feedback item 5) not declared again |
| **2026-09-17** (submitted 2026-09-15 08:52) | v5 — correct S2S text + v4 **product UI** video | Same Policy 1.6 boilerplate; Direct Support later: need **backend-only** screencast |
| **2026-09-22** | v6 package prepared | Backend terminal screencast + new copy; await human GO before Request again |

### Reject #3 root cause

Reviewer feedback item 5 was an explicit waiver we failed to invoke:

> *If your app is a server-to-server app OR your app is using system user token to access Meta API, please indicate it **in your next submission** so that we're aware that frontend Meta login authentication flow is not visible.*

Items 1 and 2 of the same feedback demand "the complete Meta login flow" and "a user granting app access" — impossible for a System User flow. Item 5 waives them, but only if declared **in the written submission**. The submitted text still read *"with a user who administers the business portfolio…"*, so the reviewer saw a text promising a login flow next to a video without one.

Second defect: the live demo was **unusable in a real browser** during all three submissions (see CORS note below). If the reviewer opened the URL and clicked **Discover Business Assets**, they got `Failed to fetch`.

Third, and probably the most damaging: **the URL in the submission pointed at the wrong page.** The reviewer instructions read `https://omnimsg.io/app-review/business-management.html` — with a `.html` suffix. That path returned HTTP 200 but served a stale v1/v2 recording aid, not the demo. See the section below.

**Form/CORS/URL defects from earlier attempts were fixed.** v6 replaces the product-UI screencast approach per Direct Support (see status at top).

---

## Stale public review pages — removed 2026-09-07

Two leftover pages from the v1/v2 attempts were still live on `omnimsg.io` and were **never in git** — they only existed in the prod file tree, so no code review ever caught them.

| Path | What a reviewer saw |
|------|---------------------|
| `/app-review/business-management.html` — **the URL used in the submission** | A recording teleprompter: "Play auto (for recording)", "Prefer also showing **Graph API Explorer**", plus a voiceover script. Rendered broken (`${s.title}` unevaluated). |
| `/app-review/business-management-v2-checklist.html` | The v2 shot checklist: "Show the complete login flow", "Admin signs in to Meta to authorize OmniMsg", "User grants business_management to OmniMsg". |

A reviewer following the submitted link therefore landed on a page that was not the product, that advertised Graph API Explorer and a login/grant flow we do not have, and that looked like a staged script. Both contradict the v3 screencast directly.

Both files were moved to `/opt/stacks/omnimsgio/.app-review-archive/` on the server (outside `apps/web/public/`) and the `web` image was rebuilt. The v3 HTML backup was also served from `public/` and was archived with them.

Verified after rebuild: both stale paths return **404**, no page on the site still contains "Graph API Explorer" / "voiceover" / "Play auto", and the real demo still returns 200 with the legend, 14 tooltipped elements and A/B/C all HTTP 200.

**URL forms — only these are correct:**

| URL | Result |
|-----|--------|
| `https://omnimsg.io/app-review/business-management` | **200** — the demo. Use this one. |
| `https://omnimsg.io/app-review/business-management/` | 308 → 200 |
| `https://omnimsg.io/app-review/business-management/index.html` | 200 |
| `https://omnimsg.io/app-review/business-management.html` | **301 → the demo** since 2026-09-07 (previously served the stale page) |
| `https://omnimsg.io/app-review/business-management-v2-checklist.html` | **301 → the demo** |

The two legacy `.html` paths are redirected rather than left as 404s, because the already-rejected submissions still contain those links: a reviewer opening submission history lands on the current demo instead of a dead page. The map lives in `apps/web/src/middleware.ts` (`LEGACY_APP_REVIEW_REDIRECTS`), applied before the existing `/app-review/*` rewrite. Verified end to end in a browser: entering through the legacy URL lands on the canonical path and **Discover Business Assets** returns A/B/C all HTTP 200.

Use the suffix-free URL in every submission field regardless — the redirect is a safety net, not the canonical link.

---

## Prod CORS defect — fixed 2026-09-07

`https://omnimsg.io` was missing from the gateway allow-list, so the browser preflight failed and the demo could not call the API.

| | Before | After |
|---|--------|-------|
| `.env` line 26 on `dedicated-hel1` | `CORS_ALLOWED_ORIGINS=https://app.omnimsg.io` | `…=https://app.omnimsg.io,https://omnimsg.io,https://www.omnimsg.io` |
| `OPTIONS /app-review/bm-discover` (Origin `https://omnimsg.io`) | `400 Disallowed CORS origin` | `200` + `access-control-allow-origin: https://omnimsg.io` |
| Discover click in a normal browser (no bypass flags) | `Failed to fetch` | A/B/C all **HTTP 200**, no console errors |

Applied by editing prod `.env` (backup `.env.bak.cors.20260906-232909`) and recreating the `gateway` container. The code default in `settings.py` already contained the apex origin; only the prod override was stale. Keep prod `.env` in sync with `.env.example` when adding public browser surfaces.

---

## System User token (2026-08-27) — PASS

| Check | Local / prod |
|-------|----------------|
| `debug_token` type | `SYSTEM_USER` |
| System user | `omnimsg_api` |
| App ID | `3492919917530282` |
| `business_management` in scopes | **Present** (+ WA scopes, `manage_app_solution`, etc.) |
| `expires_at` | `0` (Never) |

Live Graph with System User on prod (2026-08-27):

| Call | Endpoint | HTTP | Result |
|------|----------|------|--------|
| A | `GET /v21.0/me/businesses?fields=id,name` | 200 | `data: []` — expected for System User |
| B | `GET /v21.0/1329905112443890?fields=id,name` | 200 | Finestar Hospitality |
| C | `GET /v21.0/1329905112443890/owned_whatsapp_business_accounts?fields=id,name` | 200 | stay_hr, Test WABA, Finestar Hospitality |

Evidence archive: `graph-response.json` (USER token A/B/C from 2026-08-02 App Review counter; still valid for Testing counter history).

---

## Implementation (merged `main`)

| Piece | Path / endpoint |
|-------|-----------------|
| Demo UI | `apps/web/public/app-review/business-management/index.html` |
| Routing | `apps/web/src/middleware.ts` — `/app-review/*` static, rewrite to `index.html`, plus `LEGACY_APP_REVIEW_REDIRECTS` for the dead v1/v2 `.html` URLs |
| Gateway | `POST /app-review/bm-discover`, legacy paste UI `/app-review/bm-runner` (not in screencast) |
| Flags | `FEATURE_APP_REVIEW_BM_DEMO=true`, `META_BUSINESS_ACCESS_TOKEN` on gateway |
| CORS | `CORS_ALLOWED_ORIGINS` must include `https://omnimsg.io` for the demo to work in a browser |

---

## v4 preparation (2026-09-07)

### Demo UI — tooltips and legend (feedback item 4)

`apps/web/public/app-review/business-management/index.html` gained in-page tooltips and a "How to read the results below" legend. Tooltips are CSS-driven (`.tip` + `data-tip`) rather than native `title=`, because native tooltips are drawn by the OS and never appear in a screen recording. They open on hover, on keyboard focus, and on a scripted `.tip-show` class so the capture can hold them open.

Tooltipped elements: the **Discover Business Assets** button, the System User note, each **Call A/B/C** label, each **Primary / Informative** pill, each request path and each **HTTP** status. The legend defines Call A/B/C, Primary, Informative, HTTP 200, and both code blocks.

### Screencast

| | |
|---|---|
| File | `recordings/omnimsg-business-management-v4.mp4` (4.2 MB) |
| Length / size | 82.9 s, 1920×1080, H.264, no audio |
| Captions | Burned-in English; positioned at the top during the results section so JSON is never covered |
| Extras | Synthetic cursor (Playwright captures no real pointer) and a blue ring on the panel each caption refers to |
| Reproduce | `node recordings/record-v4.mjs` then the ffmpeg line in [screencast-script.md](screencast-script.md) §6 |
| UI check without prod | `node recordings/verify-ui.mjs` — serves `apps/web/public` and stubs the backend probe |

Shot-by-shot breakdown is in [screencast-script.md](screencast-script.md) §4. Media and the capture scripts stay in `recordings/`, which is gitignored.

### Deploy note

The UI change was copied to `dedicated-hel1` and the `web` image rebuilt, but **is not committed to git yet**. Prod is therefore ahead of `main`, and `.deployed-bm-sha` still reads `971ed150…`. Commit and merge the `index.html` change to bring them back in sync.

Prod is a plain file tree, not a git checkout, which is how the stale pages above survived unnoticed. Anything under `apps/web/public/` is publicly served — never leave backups or scratch pages there. Archived copies now live in `/opt/stacks/omnimsgio/.app-review-archive/`, and there are still unrelated stray files at the prod repo root (`index.html`, `main.py`, `middleware.ts`, `app_review_bm_runner.py`) left over from earlier file-copy deploys; they are outside any served directory but worth cleaning up.

---

## Definition of Done (Phase 1)

- [x] Pre-check portfolio + app BM permission + system user role + verification
- [x] Graph test calls A/B/C HTTP 200 (System User on prod)
- [x] System User token includes `business_management`
- [x] S2S demo merged to `main` and deployed to `dedicated-hel1`
- [x] App Review URLs live (all three URL forms → 200)
- [x] **v3 screencast** recorded and uploaded to Meta
- [x] Advanced Review **submitted** (3× — last result 2026-09-05, not approved)
- [x] Live demo usable in a normal browser (CORS fixed 2026-09-07)
- [x] Demo UI tooltips + legend deployed (feedback item 4)
- [x] **v4 screencast** recorded (superseded)
- [x] **v6 backend S2S screencast** recorded
- [x] v6 submission copy written
- [ ] Commit + merge web tooltip/middleware changes still ahead of `main` on prod
- [ ] Dashboard Basic Settings checklist confirmed
- [ ] v6 text + video submitted (**Request again**) after human GO
- [ ] `business_management` **Approved** — optional upside, not a dependency
- [ ] Kickoff tracker updated with the outcome

Phase 1 no longer waits on BM Advanced approval for shipping. Phase 2 (credit-line attach) is blocked on **Solution Partner status + Extended Credit Line**. If v6 is rejected after following Direct Support, stop iterating unless a real Graph call fails with `#200`.

### Cleanup once the review is closed either way

- Disable `FEATURE_APP_REVIEW_BM_DEMO` / `FEATURE_APP_REVIEW_BM_RUNNER` on `dedicated-hel1`
- Consider dropping `https://omnimsg.io` from the gateway CORS list if no other public browser surface needs it
- Revoke any User tokens pasted into earlier v1/v2 attempts

---

## Pre-check archive (2026-08-02)

Historical record before System User regen with BM:

| Check | Result |
|-------|--------|
| App has `business_management` on Testing use cases | PASS (permission present) |
| System User role | Admin on portfolio |
| Business Verification | Approved |
| System token BM scope at time | **Absent** — regen completed 2026-08-27 |
