"""Temporary App Review helpers for business_management Graph probes.

- S2S demo: POST /app-review/bm-discover (System User omnimsg_api; no browser token)
- Legacy paste UI: /app-review/bm-runner (FEATURE_APP_REVIEW_BM_RUNNER)

Disable FEATURE_APP_REVIEW_BM_DEMO / FEATURE_APP_REVIEW_BM_RUNNER after App Review.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from omnimsg_common.settings import get_settings
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_DEFAULT_BUSINESS_ID = "1329905112443890"
_RATE_WINDOW_S = 3600
_RATE_MAX = 40
_rate_hits: dict[str, list[float]] = {}

_CALL_META: list[dict[str, str]] = [
    {
        "label": "A",
        "role": "informative",
        "note": (
            "System User /me/businesses often returns an empty list; "
            "assigned Business Manager assets are read via B and C."
        ),
    },
    {
        "label": "B",
        "role": "primary",
        "note": "Read Business Manager portfolio identity.",
    },
    {
        "label": "C",
        "role": "primary",
        "note": "List WhatsApp Business Accounts owned by that business.",
    },
]

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="robots" content="noindex,nofollow" />
  <title>OmniMsg — business_management runner</title>
  <style>
    :root {
      --navy: #0a1128; --blue: #0047ab; --teal: #00c2cb; --muted: #4a5a6a;
      --line: #d7e3ec; --bg: #f7fbfd; --ok: #0a7a3e; --bad: #a11;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0; font-family: "Segoe UI", system-ui, sans-serif; color: var(--navy);
      background: linear-gradient(180deg, #e8f4f8, #fff); min-height: 100vh;
    }
    .wrap { width: min(880px, calc(100% - 2rem)); margin: 0 auto; padding: 1.5rem 0 3rem; }
    h1 { font-size: 1.45rem; margin: 0 0 0.35rem; }
    .meta { color: var(--muted); margin: 0 0 1.25rem; line-height: 1.45; }
    .card {
      background: #fff; border: 1px solid var(--line); border-radius: 0.85rem;
      padding: 1.1rem 1.2rem; margin-bottom: 1rem;
    }
    label { display: block; font-weight: 600; margin-bottom: 0.35rem; }
    input[type=text], textarea {
      width: 100%; font: inherit; padding: 0.65rem 0.75rem; border: 1px solid var(--line);
      border-radius: 0.5rem;
    }
    textarea {
      min-height: 4.5rem;
      font-family: ui-monospace, Menlo, Consolas, monospace;
      font-size: 0.85rem;
    }
    .row { display: flex; flex-wrap: wrap; gap: 0.75rem; margin-top: 0.85rem; align-items: end; }
    .row > div { flex: 1; min-width: 12rem; }
    button {
      font: inherit; cursor: pointer; border: 0; border-radius: 0.5rem;
      background: var(--blue); color: #fff; padding: 0.7rem 1.2rem; font-weight: 600;
    }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    .note {
      background: #eef7fa; border-left: 3px solid var(--teal); padding: 0.7rem 0.85rem;
      margin: 0.85rem 0 0; font-size: 0.92rem; line-height: 1.45;
    }
    .call { margin-top: 1rem; }
    .path { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 0.86rem;
      background: #f0f6fa; padding: 0.5rem 0.65rem; border-radius: 0.4rem; word-break: break-all; }
    .status { font-weight: 600; margin: 0.4rem 0; }
    .status.ok { color: var(--ok); }
    .status.bad { color: var(--bad); }
    pre {
      margin: 0.4rem 0 0; max-height: 220px; overflow: auto; background: #0a1128; color: #d7f5ff;
      border-radius: 0.65rem; padding: 0.85rem; font-size: 0.8rem; line-height: 1.4;
    }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>OmniMsg · business_management runner</h1>
    <p class="meta">
      Paste a Meta <strong>User</strong> access token that includes
      <code>business_management</code>, then Run. Results are the Graph calls used for
      App Review. Token is sent only to this OmniMsg API probe (not stored / not logged).
    </p>

    <div class="card">
      <label for="token">Access token</label>
      <textarea id="token" placeholder="EAAB… or EAAx…"
        autocomplete="off" spellcheck="false"></textarea>
      <div class="row">
        <div>
          <label for="bid">Business ID</label>
          <input id="bid" type="text" value="__BUSINESS_ID__" />
        </div>
        <div>
          <label for="ver">Graph API version</label>
          <input id="ver" type="text" value="__GRAPH_VERSION__" />
        </div>
        <button type="button" id="run">Run</button>
      </div>
      <p class="note">
        Production OmniMsg uses System User <code>omnimsg_api</code> (server-to-server) on
        <code>https://api.omnimsg.io</code>.
        This page is for App Review demonstration with a User token.
      </p>
    </div>

    <div id="out"></div>
  </div>
  <script>
    const out = document.getElementById("out");
    const runBtn = document.getElementById("run");
    runBtn.onclick = async () => {
      const access_token = document.getElementById("token").value.trim();
      let business_id = document.getElementById("bid").value.trim();
      const graph_version = document.getElementById("ver").value.trim();
      if (!access_token) { alert("Paste an access token first."); return; }
      if (!business_id) {
        business_id = "1329905112443890";
        document.getElementById("bid").value = business_id;
      }
      runBtn.disabled = true;
      out.innerHTML = "<p class='meta'>Running…</p>";
      try {
        const res = await fetch("/app-review/bm-probe", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ access_token, business_id, graph_version }),
        });
        const data = await res.json();
        if (!res.ok) {
          const detail = data.detail;
          const msg = typeof detail === "string"
            ? detail
            : (data.error || JSON.stringify(detail || data));
          out.innerHTML = "<div class='card'><p class='status bad'></p></div>";
          out.querySelector(".status").textContent = msg;
          return;
        }
        out.innerHTML = (data.calls || []).map((c) => {
          const ok = c.http_status >= 200 && c.http_status < 300;
          return "<div class='card call'><div class='path'>" + c.method + " " + c.path +
            "</div><div class='status " + (ok ? "ok" : "bad") + "'>HTTP " + c.http_status +
            "</div><pre>" + JSON.stringify(c.body, null, 2) + "</pre></div>";
        }).join("");
      } catch (e) {
        out.innerHTML = "<div class='card'><p class='status bad'></p></div>";
        out.querySelector(".status").textContent = String(e);
      } finally {
        runBtn.disabled = false;
      }
    };
  </script>
</body>
</html>
"""


class BmProbeRequest(BaseModel):
    access_token: str = Field(min_length=20, max_length=4096)
    business_id: str = Field(default=_DEFAULT_BUSINESS_ID, min_length=5, max_length=64)
    graph_version: str = Field(default="v21.0", min_length=2, max_length=16)


class BmDiscoverRequest(BaseModel):
    """S2S discover — no client token; server uses META_BUSINESS_ACCESS_TOKEN."""

    business_id: str = Field(default=_DEFAULT_BUSINESS_ID, min_length=5, max_length=64)
    graph_version: str = Field(default="", max_length=16)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("cf-connecting-ip") or request.headers.get(
        "x-forwarded-for"
    )
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _rate_allow(ip: str) -> bool:
    now = time.time()
    hits = [t for t in _rate_hits.get(ip, []) if now - t < _RATE_WINDOW_S]
    if len(hits) >= _RATE_MAX:
        _rate_hits[ip] = hits
        return False
    hits.append(now)
    _rate_hits[ip] = hits
    return True


async def _graph_get(
    client: httpx.AsyncClient,
    *,
    version: str,
    path: str,
    token: str,
) -> dict[str, Any]:
    url = f"https://graph.facebook.com/{version}{path}"
    # Prefer Authorization header so token is less likely to appear in proxy logs.
    response = await client.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        body: Any = response.json()
    except ValueError:
        body = {"raw": response.text[:2000]}
    return {
        "method": "GET",
        "path": f"/{version}{path}",
        "http_status": response.status_code,
        "body": body,
    }


def bm_graph_paths(business_id: str) -> list[str]:
    """Graph A/B/C paths used for business_management App Review."""
    bid = business_id.strip() or _DEFAULT_BUSINESS_ID
    return [
        "/me/businesses?fields=id,name",
        f"/{bid}?fields=id,name",
        f"/{bid}/owned_whatsapp_business_accounts?fields=id,name",
    ]


async def run_bm_graph_probes(
    *,
    token: str,
    business_id: str,
    version: str,
) -> list[dict[str, Any]]:
    """Run Graph A/B/C with Bearer token; never logs the token."""
    ver = version.strip().lstrip("/")
    if not ver.startswith("v"):
        ver = f"v{ver}"
    paths = bm_graph_paths(business_id)
    timeout = httpx.Timeout(20.0, connect=5.0)
    calls: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=timeout) as client:
        for idx, path in enumerate(paths):
            meta = _CALL_META[idx] if idx < len(_CALL_META) else {}
            try:
                result = await _graph_get(
                    client, version=ver, path=path, token=token
                )
            except httpx.RequestError as exc:
                logger.warning(
                    "bm-probe graph error path=%s err=%s",
                    path,
                    type(exc).__name__,
                )
                result = {
                    "method": "GET",
                    "path": f"/{ver}{path}",
                    "http_status": 0,
                    "body": {"error": "upstream_unreachable"},
                }
            else:
                logger.info(
                    "bm-probe path=%s status=%s",
                    path.split("?")[0],
                    result["http_status"],
                )
            if meta:
                result = {**meta, **result}
            calls.append(result)
    return calls


def mount_app_review_bm_runner(app: FastAPI) -> None:
    """Register BM App Review routes (S2S discover + optional paste runner)."""

    @app.post("/app-review/bm-discover", include_in_schema=False)
    async def bm_discover(request: Request) -> JSONResponse:
        """Discover BM assets using the configured System User token (S2S)."""
        settings = get_settings()
        if not settings.feature_app_review_bm_demo:
            return JSONResponse({"error": "disabled"}, status_code=404)

        ip = _client_ip(request)
        if not _rate_allow(ip):
            return JSONResponse(
                {"error": "rate_limited", "detail": "Too many probe requests"},
                status_code=429,
            )

        token = settings.meta_business_access_token.strip()
        if not token:
            return JSONResponse(
                {
                    "error": "misconfigured",
                    "detail": "META_BUSINESS_ACCESS_TOKEN is not set on the server",
                },
                status_code=503,
            )

        raw: dict[str, Any] = {}
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                parsed = await request.json()
                if isinstance(parsed, dict):
                    raw = parsed
            except Exception:
                raw = {}
        payload = BmDiscoverRequest.model_validate(raw)

        business_id = (
            payload.business_id.strip()
            or settings.meta_business_id.strip()
            or _DEFAULT_BUSINESS_ID
        )
        version = (
            payload.graph_version.strip()
            or settings.meta_graph_api_version.strip()
            or "v21.0"
        )
        calls = await run_bm_graph_probes(
            token=token,
            business_id=business_id,
            version=version,
        )
        return JSONResponse(
            {
                "auth_mode": "system_user",
                "system_user": "omnimsg_api",
                "business_id": business_id,
                "graph_version": version.lstrip("/"),
                "calls": calls,
            }
        )

    @app.get("/app-review/bm-runner", response_class=HTMLResponse, include_in_schema=False)
    async def bm_runner_page() -> HTMLResponse:
        settings = get_settings()
        if not settings.feature_app_review_bm_runner:
            return HTMLResponse("Not Found", status_code=404)
        business_id = (
            settings.meta_business_id.strip()
            if settings.meta_business_id.strip()
            else _DEFAULT_BUSINESS_ID
        )
        version = settings.meta_graph_api_version.strip() or "v21.0"
        html = (
            _HTML.replace("__BUSINESS_ID__", business_id).replace(
                "__GRAPH_VERSION__", version
            )
        )
        return HTMLResponse(
            html,
            headers={
                "Cache-Control": "no-store",
                "X-Robots-Tag": "noindex, nofollow",
            },
        )

    @app.post("/app-review/bm-probe", include_in_schema=False)
    async def bm_probe(payload: BmProbeRequest, request: Request) -> JSONResponse:
        settings = get_settings()
        if not settings.feature_app_review_bm_runner:
            return JSONResponse({"error": "disabled"}, status_code=404)

        ip = _client_ip(request)
        if not _rate_allow(ip):
            return JSONResponse(
                {"error": "rate_limited", "detail": "Too many probe requests"},
                status_code=429,
            )

        business_id = payload.business_id.strip()
        token = payload.access_token.strip()
        calls = await run_bm_graph_probes(
            token=token,
            business_id=business_id,
            version=payload.graph_version,
        )
        return JSONResponse({"calls": calls})
