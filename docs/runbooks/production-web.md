# Production web (`omnimsg.io` / `www` / `app`)

Deploy target: **dedicated-hel1** Traefik on Docker network `proxy` (same pattern as the [API gateway](production-gateway.md)).

## Hosts

| Host | Surface |
|------|---------|
| `omnimsg.io`, `www.omnimsg.io` | Promo landing (`apps/web` → `/www`) |
| `app.omnimsg.io` | Portal shell (`apps/web` → `/portal`) — no auth yet |

App: [`apps/web`](../../apps/web) (Next.js App Router, standalone Docker image).

Public routes: `/` (promo), `/privacy` (Privacy Policy — Meta App Review Basic settings URL `https://omnimsg.io/privacy`).

Portal Connect WhatsApp is gated by runtime env `FEATURE_EMBEDDED_SIGNUP=true` (see `.env.example`). Also set `META_APP_ID`, `META_ES_CONFIG_ID`, and `API_BASE_URL`.

## Bring-up

```bash
# On dedicated-hel1, from /opt/stacks/omnimsgio
docker compose -f docker/production/docker-compose.yml --env-file .env up -d --build web
```

Compose labels: `Host(\`omnimsg.io\`) || Host(\`www.omnimsg.io\`)` and `Host(\`app.omnimsg.io\`)`, entrypoint `websecure`, `tls.certresolver=lecf`, port `3000`.

## DNS

Cloudflare zone `omnimsg.io` — A/AAAA for apex, `www`, and `app` → `dedicated-hel1` (`65.108.196.92` / `2a01:4f9:1a:9840::2`), **proxied**. Ops note: `/opt/stacks/ops/omnimsgio-meta-sp-kickoff.md` §4.

## Local Traefik

Development Compose publishes:

- `https://omnimsgio-web.localhost` — marketing
- `https://omnimsgio-app.localhost` — portal shell
