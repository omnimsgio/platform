"""Gateway: Bearer API-key auth, rate limit, reverse-proxy to the API."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from omnimsg_common.ids import new_id
from omnimsg_common.queue import create_redis_client
from omnimsg_common.settings import get_settings

logger = logging.getLogger(__name__)

HOP_BY_HOP = {"host", "content-length", "transfer-encoding", "connection"}
STRIP_TRUSTED = {"x-tenant-id", "x-api-key-id"}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    timeout = httpx.Timeout(30.0, connect=5.0)
    app.state.http = httpx.AsyncClient(base_url=settings.api_url.rstrip("/"), timeout=timeout)
    logger.info("gateway ready; proxying to %s", settings.api_url)
    try:
        yield
    finally:
        await app.state.http.aclose()


app = FastAPI(
    title="OmniMsg Gateway",
    version="0.1.0",
    lifespan=lifespan,
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
    )


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


@app.get("/health")
async def health() -> dict[str, str]:
    """Edge liveness for Traefik / load balancers (public)."""
    settings = get_settings()
    return {"status": "ok", "version": settings.app_version}


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
