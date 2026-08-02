"""Gateway: Bearer API-key auth, rate limit, reverse-proxy to the API."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from omnimsg_common.db.models import TenantWhatsappAccount
from omnimsg_common.db.session import session_scope
from omnimsg_common.ids import new_id
from omnimsg_common.openapi_contract import (
    LoadedOpenAPIContract,
    OpenAPIContractError,
    load_openapi_contract,
    resolve_contract_path,
)
from omnimsg_common.proxy_urls import rewrite_internal_location
from omnimsg_common.queue import create_redis_client, enqueue_json
from omnimsg_common.settings import get_settings
from omnimsg_common.whatsapp_lifecycle import messaging_ready_statuses
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware

from omnimsg_gateway.meta_webhook import (
    classify_webhook_kind,
    extract_external_event_id,
    extract_phone_number_id,
    parse_webhook_json,
    verify_meta_signature,
    webhook_payload_redis_key,
)

logger = logging.getLogger(__name__)

HOP_BY_HOP = {"host", "content-length", "transfer-encoding", "connection"}
STRIP_TRUSTED = {"x-tenant-id", "x-api-key-id"}
# Keep raw webhook bodies long enough for worker retries / late status processing.
WEBHOOK_PAYLOAD_TTL_SECONDS = 7 * 24 * 60 * 60
OPENAPI_CACHE_CONTROL = "public, max-age=300"
DOCS_CSP = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "font-src 'self' https://cdn.jsdelivr.net data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Baseline security headers for the public API edge (ADR-0021)."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        path = request.url.path
        if path in {"/docs", "/redoc", "/docs/", "/redoc/"}:
            response.headers["Content-Security-Policy"] = DOCS_CSP
        correlation = request.headers.get("x-correlation-id") or getattr(
            request.state, "correlation_id", None
        )
        if correlation and "x-correlation-id" not in {k.lower() for k in response.headers}:
            response.headers["X-Correlation-Id"] = correlation
        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    try:
        path = (
            resolve_contract_path(settings.openapi_contract_path or None)
            if settings.openapi_contract_path
            else resolve_contract_path()
        )
        contract = load_openapi_contract(path)
    except OpenAPIContractError:
        logger.exception("openapi contract load failed; refusing to start")
        raise
    app.state.openapi_contract = contract
    timeout = httpx.Timeout(30.0, connect=5.0)
    app.state.http = httpx.AsyncClient(base_url=settings.api_url.rstrip("/"), timeout=timeout)
    logger.info(
        "gateway ready; proxying to %s; contract=%s version=%s",
        settings.api_url,
        contract.path,
        contract.contract_version,
    )
    try:
        yield
    finally:
        await app.state.http.aclose()


app = FastAPI(
    title="OmniMsg Gateway",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(SecurityHeadersMiddleware)

# Portal (app.omnimsg.io) calls the public API from the browser; without CORS
# the browser surfaces TypeError "Failed to fetch" on Connect WhatsApp.
_cors_origins = get_settings().cors_origins_list
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Correlation-Id",
            "X-Idempotency-Key",
        ],
        expose_headers=["X-Correlation-Id"],
    )


def _error_response(
    status_code: int,
    *,
    code: str,
    message: str,
    correlation_id: str,
    retryable: bool = False,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "retryable": retryable,
                "correlation_id": correlation_id,
            }
        },
        headers={"X-Correlation-Id": correlation_id},
    )


def _contract(request: Request) -> LoadedOpenAPIContract:
    return request.app.state.openapi_contract


def _extract_bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization")
    if not auth:
        return None
    scheme, _, token = auth.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _check_rate_limit(api_key_id: str) -> bool:
    """Fixed-window rate limit. Returns True if the request is allowed."""
    settings = get_settings()
    client = create_redis_client(settings)
    try:
        key = settings.rate_limit_key(api_key_id)
        count = int(client.incr(key))
        if count == 1:
            client.expire(key, 60)
        return count <= settings.rate_limit_per_minute
    finally:
        client.close()


@app.get("/")
async def discovery(request: Request) -> dict[str, str]:
    """Public discovery document (ADR-0021)."""
    settings = get_settings()
    contract = _contract(request)
    return {
        "status": "ok",
        "name": "OmniMsg API",
        "version": settings.app_version,
        "environment": settings.app_env,
        "contract_version": contract.contract_version,
        "docs": "/docs",
        "redoc": "/redoc",
        "openapi": "/openapi.json",
        "health": "/health",
        "version_url": "/version",
    }


@app.get("/version")
async def version(request: Request) -> dict[str, str]:
    """Build/deploy metadata for ops debugging."""
    settings = get_settings()
    contract = _contract(request)
    return {
        "version": settings.app_version,
        "git_sha": settings.git_sha,
        "build_date": settings.build_date,
        "environment": settings.app_env,
        "contract_version": contract.contract_version,
    }


@app.get("/health")
async def health() -> dict[str, str]:
    """Edge liveness for Traefik / load balancers (public; no dependency checks)."""
    settings = get_settings()
    return {"status": "ok", "version": settings.app_version}


@app.get("/openapi.json")
async def openapi_json(request: Request) -> Response:
    """Serve packages/contracts OpenAPI SSOT (never FastAPI runtime schema)."""
    contract = _contract(request)
    if_none_match = request.headers.get("if-none-match")
    if if_none_match and if_none_match.strip() == contract.etag:
        return Response(
            status_code=304,
            headers={
                "ETag": contract.etag,
                "Cache-Control": OPENAPI_CACHE_CONTROL,
            },
        )
    return Response(
        content=contract.json_bytes,
        media_type="application/json",
        headers={
            "ETag": contract.etag,
            "Cache-Control": OPENAPI_CACHE_CONTROL,
        },
    )


@app.get("/docs", include_in_schema=False)
async def swagger_docs() -> HTMLResponse:
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="OmniMsg API · Docs",
    )


@app.get("/redoc", include_in_schema=False)
async def redoc_docs() -> HTMLResponse:
    return get_redoc_html(
        openapi_url="/openapi.json",
        title="OmniMsg API · ReDoc",
    )


@app.get("/v1/health")
async def proxy_v1_health(request: Request) -> Response:
    """Public API readiness probe — no Bearer (ADR-0021)."""
    correlation_id = request.headers.get("x-correlation-id") or new_id("req")
    request.state.correlation_id = correlation_id
    client: httpx.AsyncClient = request.app.state.http
    headers = {"x-correlation-id": correlation_id}
    try:
        upstream = await client.get("/v1/health", headers=headers)
    except httpx.RequestError as exc:
        logger.warning("v1 health upstream unreachable: %s", exc)
        return _error_response(
            502,
            code="upstream_failure",
            message="API upstream unreachable",
            correlation_id=correlation_id,
            retryable=True,
        )
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers={
            key: value
            for key, value in upstream.headers.items()
            if key.lower()
            not in {
                "content-encoding",
                "content-length",
                "transfer-encoding",
                "connection",
            }
        }
        | {"X-Correlation-Id": correlation_id},
        media_type=upstream.headers.get("content-type"),
    )


def _admin_unauthorized() -> Response:
    return Response(
        status_code=401,
        content=b"Unauthorized",
        headers={"WWW-Authenticate": 'Basic realm="OmniMsg Ops"'},
        media_type="text/plain",
    )


@app.api_route(
    "/admin/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
@app.api_route(
    "/admin",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def proxy_admin(request: Request, path: str = "") -> Response:
    """Ops admin proxy — HTTP Basic only (ADR-0022); never tenant Bearer."""
    settings = get_settings()
    correlation_id = request.headers.get("x-correlation-id") or new_id("req")
    request.state.correlation_id = correlation_id

    if not settings.admin_enabled:
        return _error_response(
            503,
            code="admin_disabled",
            message="Admin is not configured",
            correlation_id=correlation_id,
        )

    auth = request.headers.get("authorization")
    if not auth or not auth.lower().startswith("basic "):
        return _admin_unauthorized()
    try:
        import base64
        import hmac as hmac_mod

        raw = base64.b64decode(auth.split(" ", 1)[1].strip()).decode("utf-8")
        user, _, password = raw.partition(":")
        if len(user) != len(settings.admin_username) or len(password) != len(
            settings.admin_password
        ):
            return _admin_unauthorized()
        user_ok = hmac_mod.compare_digest(user, settings.admin_username)
        pass_ok = hmac_mod.compare_digest(password, settings.admin_password)
        if not (user_ok and pass_ok):
            return _admin_unauthorized()
    except (ValueError, UnicodeDecodeError):
        return _admin_unauthorized()

    suffix = path.strip("/")
    url = f"/admin/{suffix}" if suffix else "/admin/"
    body = await request.body()
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in HOP_BY_HOP
    }
    headers["x-correlation-id"] = correlation_id
    # Ensure admin URL generation behind Traefik uses the public host.
    if "x-forwarded-host" not in {k.lower() for k in headers}:
        headers["x-forwarded-host"] = request.headers.get("host") or "api.omnimsg.io"
    if "x-forwarded-proto" not in {k.lower() for k in headers}:
        headers["x-forwarded-proto"] = request.url.scheme or "https"
    client: httpx.AsyncClient = request.app.state.http
    try:
        upstream = await client.request(
            request.method,
            url,
            content=body,
            headers=headers,
            params=request.query_params,
        )
    except httpx.RequestError as exc:
        logger.warning("admin upstream unreachable: %s", exc)
        return _error_response(
            502,
            code="upstream_failure",
            message="API upstream unreachable",
            correlation_id=correlation_id,
            retryable=True,
        )
    out_headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower()
        not in {
            "content-encoding",
            "content-length",
            "transfer-encoding",
            "connection",
        }
    }
    loc = out_headers.get("location") or out_headers.get("Location")
    if loc:
        public_origin = str(request.base_url).rstrip("/")
        # Prefer forwarded public origin when present.
        fwd_host = (
            request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
        ).split(",")[0].strip()
        fwd_proto = (
            request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
        ).split(",")[0].strip()
        if fwd_host:
            public_origin = f"{fwd_proto}://{fwd_host}"
        rewritten = rewrite_internal_location(loc, public_origin=public_origin)
        # Header key casing from httpx may vary.
        for key in list(out_headers):
            if key.lower() == "location":
                out_headers[key] = rewritten
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=out_headers | {"X-Correlation-Id": correlation_id},
        media_type=upstream.headers.get("content-type"),
    )


@app.get("/webhooks/meta/whatsapp")
async def meta_whatsapp_verify(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> Response:
    """Meta hub challenge verification (public; no Bearer)."""
    settings = get_settings()
    expected = settings.meta_verify_token
    if (
        hub_mode == "subscribe"
        and expected
        and hub_verify_token == expected
        and hub_challenge is not None
        and hub_challenge != ""
    ):
        return PlainTextResponse(content=hub_challenge, status_code=200)
    logger.warning("meta webhook verify rejected mode=%s", hub_mode)
    return Response(status_code=403)


@app.post("/webhooks/meta/whatsapp")
async def meta_whatsapp_ingest(request: Request) -> Response:
    """Verify HMAC, resolve tenant, enqueue inbound event, return 200 quickly."""
    settings = get_settings()
    correlation_id = request.headers.get("x-correlation-id") or new_id("req")
    body = await request.body()
    signature = request.headers.get("x-hub-signature-256")

    if not verify_meta_signature(
        app_secret=settings.meta_app_secret,
        body=body,
        signature_header=signature,
    ):
        logger.warning(
            "meta webhook bad signature correlation_id=%s",
            correlation_id,
        )
        return _error_response(
            403,
            code="forbidden",
            message="Invalid Meta webhook signature",
            correlation_id=correlation_id,
        )

    payload = parse_webhook_json(body)
    if payload is None:
        # Signature was valid; acknowledge to avoid Meta retries on malformed body.
        logger.warning(
            "meta webhook invalid json correlation_id=%s",
            correlation_id,
        )
        return Response(status_code=200)

    phone_number_id = extract_phone_number_id(payload)
    if not phone_number_id:
        logger.warning(
            "meta webhook missing phone_number_id correlation_id=%s",
            correlation_id,
        )
        return Response(status_code=200)

    tenant_id = _resolve_whatsapp_tenant(phone_number_id)
    if tenant_id is None:
        logger.warning(
            "meta webhook unknown phone_number_id=%s correlation_id=%s",
            phone_number_id,
            correlation_id,
        )
        return Response(status_code=200)

    received_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    payload_id = new_id("wh")
    event_id = new_id("evt")
    kind = classify_webhook_kind(payload)
    external_event_id = extract_external_event_id(payload)

    event_data: dict[str, Any] = {
        "provider": "meta_whatsapp",
        "channel": "whatsapp",
        "received_at": received_at,
        "payload_ref": payload_id,
        "kind": kind,
    }
    if external_event_id:
        event_data["external_event_id"] = external_event_id

    event: dict[str, Any] = {
        "event_id": event_id,
        "event_type": "webhook.inbound.received.v1",
        "occurred_at": received_at,
        "tenant_id": tenant_id,
        "correlation_id": correlation_id,
        "data": event_data,
    }
    job: dict[str, Any] = {
        "job_type": "inbound_webhook",
        "event": event,
        "payload": payload,
    }

    redis_key = webhook_payload_redis_key(
        redis_key_prefix=settings.redis_key_prefix,
        payload_id=payload_id,
    )
    try:
        client = create_redis_client(settings)
        try:
            client.setex(redis_key, WEBHOOK_PAYLOAD_TTL_SECONDS, body)
            enqueue_json(client, settings.inbound_queue_key, job)
        finally:
            client.close()
    except Exception:  # noqa: BLE001 — still ack Meta; log for ops
        logger.exception(
            "meta webhook enqueue failed phone_number_id=%s tenant_id=%s correlation_id=%s",
            phone_number_id,
            tenant_id,
            correlation_id,
        )
        return Response(status_code=200)

    logger.info(
        "meta webhook enqueued phone_number_id=%s tenant_id=%s kind=%s "
        "payload_ref=%s correlation_id=%s",
        phone_number_id,
        tenant_id,
        kind,
        payload_id,
        correlation_id,
    )
    return Response(status_code=200)


def _resolve_whatsapp_tenant(phone_number_id: str) -> str | None:
    """Look up messaging-ready tenant for a Meta phone_number_id."""
    ready = messaging_ready_statuses()
    with session_scope() as session:
        row = session.scalars(
            select(TenantWhatsappAccount).where(
                TenantWhatsappAccount.phone_number_id == phone_number_id,
                TenantWhatsappAccount.status.in_(ready),
            )
        ).first()
        if row is None:
            return None
        return row.tenant_id


@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_v1(path: str, request: Request) -> Response:
    """Authenticate, rate-limit, then forward /v1/* to the internal API."""
    correlation_id = request.headers.get("x-correlation-id") or new_id("req")
    token = _extract_bearer(request)
    if token is None:
        return _error_response(
            401,
            code="unauthorized",
            message="Missing or invalid Authorization Bearer token",
            correlation_id=correlation_id,
        )

    client: httpx.AsyncClient = request.app.state.http
    try:
        resolve = await client.post(
            "/internal/v1/auth/resolve",
            json={"api_key": token},
        )
    except httpx.RequestError as exc:
        logger.warning("auth resolve unreachable: %s", exc)
        return _error_response(
            502,
            code="upstream_failure",
            message="API upstream unreachable",
            correlation_id=correlation_id,
            retryable=True,
        )

    if resolve.status_code != 200:
        try:
            body = resolve.json()
            if isinstance(body, dict) and "error" in body:
                return JSONResponse(status_code=401, content=body)
        except ValueError:
            pass
        return _error_response(
            401,
            code="unauthorized",
            message="Invalid API key",
            correlation_id=correlation_id,
        )

    resolved = resolve.json()
    tenant_id = resolved.get("tenant_id")
    api_key_id = resolved.get("api_key_id")
    if not tenant_id or not api_key_id:
        return _error_response(
            401,
            code="unauthorized",
            message="Invalid API key",
            correlation_id=correlation_id,
        )

    try:
        allowed = _check_rate_limit(api_key_id)
    except Exception as exc:  # noqa: BLE001 — fail closed on Redis errors
        logger.warning("rate limit check failed: %s", exc)
        return _error_response(
            502,
            code="upstream_failure",
            message="Rate limit store unreachable",
            correlation_id=correlation_id,
            retryable=True,
        )

    if not allowed:
        return _error_response(
            429,
            code="rate_limited",
            message="Rate limit exceeded",
            correlation_id=correlation_id,
            retryable=True,
        )

    url = f"/v1/{path}"
    body = await request.body()
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in HOP_BY_HOP and key.lower() not in STRIP_TRUSTED
    }
    headers.pop("authorization", None)
    headers["x-tenant-id"] = tenant_id
    headers["x-api-key-id"] = api_key_id
    if "x-correlation-id" not in {k.lower() for k in headers}:
        headers["x-correlation-id"] = correlation_id

    try:
        upstream = await client.request(
            request.method,
            url,
            content=body,
            headers=headers,
            params=request.query_params,
        )
    except httpx.RequestError as exc:
        logger.warning("upstream api unreachable: %s", exc)
        return _error_response(
            502,
            code="upstream_failure",
            message="API upstream unreachable",
            correlation_id=correlation_id,
            retryable=True,
        )

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers={
            key: value
            for key, value in upstream.headers.items()
            if key.lower()
            not in {
                "content-encoding",
                "content-length",
                "transfer-encoding",
                "connection",
            }
        },
        media_type=upstream.headers.get("content-type"),
    )


def run() -> None:
    logging.basicConfig(level=get_settings().log_level)
    uvicorn.run("omnimsg_gateway.main:app", host="0.0.0.0", port=8000, factory=False)


if __name__ == "__main__":
    run()
