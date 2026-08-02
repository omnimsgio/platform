# Meta WhatsApp webhook fields — subscribe + Test evidence

**Product:** OmniMsg / FinestAR  
**App:** OmniMsg (`3492919917530282`)  
**Callback:** `https://api.omnimsg.io/webhooks/meta/whatsapp`  
**Runbook:** [production-gateway.md](../../runbooks/production-gateway.md)  
**Gateway classifier:** `apps/gateway/omnimsg_gateway/meta_webhook.py` (`classify_webhook_kind`)

Dashboard “Test” samples from **2026-08-02** (Europe/Zagreb). Ops evidence only — not product fixtures. No tokens or secrets.

## Recommended subscribed fields

| Field | Why |
|-------|-----|
| `messages` | Inbound + delivery statuses (required) |
| `account_update` | WABA / account lifecycle |
| `account_review_update` | Account review decisions |
| `business_capability_update` | Capability / limit changes |
| `message_template_status_update` | Template approve / reject |
| `phone_number_quality_update` | Quality / messaging tier |
| `phone_number_name_update` | Verified display name |
| `partner_solutions` | Solution Partner solution events |

Already present from earlier Coexistence defaults (leave if harmless): `history`, `smb_app_state_sync`, `smb_message_echoes`.

## Incoming identity shapes (`messages`)

- **Not opted-in:** `wa_id` + `from` (+ optional `parent_*`)
- **Opted-in (phone unavailable):** no `wa_id` / `from`; `username` + `user_id` / `from_user_id`
- **Opted-in (phone available):** `username` **and** `wa_id` / `from`

## Tested samples

| Field | Version | Test options | Last Test OK | Sample file |
|-------|---------|--------------|--------------|-------------|
| `account_update` | v26.0 | — | 2026-08-02 18:10:28 | [account_update.sample.json](account_update.sample.json) |
| `account_review_update` | v26.0 | — | 2026-08-02 18:12:09 | [account_review_update.sample.json](account_review_update.sample.json) |
| `messages` | v26.0 | Incoming; Not opted-in; parent **off** | 2026-08-02 18:14:56 | [messages.incoming_text.sample.json](messages.incoming_text.sample.json) |
| `messages` | v26.0 | Incoming; Not opted-in; parent **on** | 2026-08-02 18:17:17 | [messages.incoming_text.parent_user_id.sample.json](messages.incoming_text.parent_user_id.sample.json) |
| `messages` | v26.0 | Incoming; Opted-in (phone unavailable); parent **off** | 2026-08-02 18:19:53 | [messages.incoming_text.opted_in_phone_unavailable.sample.json](messages.incoming_text.opted_in_phone_unavailable.sample.json) |
| `messages` | v26.0 | Incoming; Opted-in (phone unavailable); parent **on** | 2026-08-02 18:21:21 | [messages.incoming_text.opted_in_phone_unavailable.parent_user_id.sample.json](messages.incoming_text.opted_in_phone_unavailable.parent_user_id.sample.json) |
| `messages` | v26.0 | Incoming; Opted-in (phone available); parent **off** | 2026-08-02 18:22:32 | [messages.incoming_text.opted_in_phone_available.sample.json](messages.incoming_text.opted_in_phone_available.sample.json) |
| `messages` | v26.0 | Incoming; Opted-in (phone available); parent **on** | 2026-08-02 18:23:30 | [messages.incoming_text.opted_in_phone_available.parent_user_id.sample.json](messages.incoming_text.opted_in_phone_available.parent_user_id.sample.json) |
| `messages` | v26.0 | Status **sent**; Not opted-in; to phone; parent **off** | 2026-08-02 18:27:18 | [messages.status_sent.sample.json](messages.status_sent.sample.json) |
| `messages` | v26.0 | Status **sent**; Not opted-in; to phone; parent **on** | 2026-08-02 18:29:09 | [messages.status_sent.parent_user_id.sample.json](messages.status_sent.parent_user_id.sample.json) |
| `messages` | v26.0 | Status **sent**; Not opted-in; to **BSUID**; parent **off** | 2026-08-02 18:32:00 | [messages.status_sent.bsuid.sample.json](messages.status_sent.bsuid.sample.json) |
| `messages` | v26.0 | Status **sent**; Not opted-in; to **BSUID**; parent **on** | 2026-08-02 18:32:57 | [messages.status_sent.bsuid.parent_user_id.sample.json](messages.status_sent.bsuid.parent_user_id.sample.json) |
| `messages` | v26.0 | Status **sent**; to phone; parent **off**; contact **user_id only** | 2026-08-02 18:34:09 | [messages.status_sent.phone.contact_user_id_only.sample.json](messages.status_sent.phone.contact_user_id_only.sample.json) |
| `messages` | v26.0 | Status **sent**; to phone; parent **on**; contact **user_id only** | 2026-08-02 18:35:11 | [messages.status_sent.phone.contact_user_id_only.parent_user_id.sample.json](messages.status_sent.phone.contact_user_id_only.parent_user_id.sample.json) |
| `messages` | v26.0 | Status **delivered**; Not opted-in; to **BSUID**; parent **on** | 2026-08-02 18:36:20 | [messages.status_delivered.bsuid.parent_user_id.sample.json](messages.status_delivered.bsuid.parent_user_id.sample.json) |
| `messages` | v26.0 | Status **read**; Not opted-in; to phone; parent **off** | 2026-08-02 18:36:46 | [messages.status_read.sample.json](messages.status_read.sample.json) |
| `business_capability_update` | v26.0 | — | 2026-08-02 18:38:00 | [business_capability_update.sample.json](business_capability_update.sample.json) |
| `message_template_status_update` | v26.0 | — | 2026-08-02 18:39:43 | [message_template_status_update.sample.json](message_template_status_update.sample.json) |
| `phone_number_quality_update` | v26.0 | — | 2026-08-02 18:41:14 | [phone_number_quality_update.sample.json](phone_number_quality_update.sample.json) |
| `phone_number_name_update` | v26.0 | — | 2026-08-02 18:42:17 | [phone_number_name_update.sample.json](phone_number_name_update.sample.json) |
| `partner_solutions` | v26.0 | — | 2026-08-02 18:43:32 | [partner_solutions.sample.json](partner_solutions.sample.json) |

## Notes

- Status **sent** samples often include `conversation` + `pricing`; **delivered** may omit `pricing`; **read** is minimal (no conversation/pricing).
- Phone vs BSUID status: `recipient_id` vs `recipient_user_id`.
- Contact **user_id only** status samples: Username scenario not recorded in Dashboard paste — label as unknown until confirmed.
