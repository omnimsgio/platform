"""Gateway: edge health probe and reverse-proxy to the API."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from omnimsg_common.settings import get_settings

logger = logging.getLogger(__name__)


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


@app.get("/health")
async def health() -> dict[str, str]:
    """Edge liveness for Traefik / load balancers."""
    settings = get_settings()
    return {"status": "ok", "version": settings.app_version}


@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_v1(path: str, request: Request) -> Response:
    """Forward /v1/* to the internal API (Client → Traefik → gateway → api)."""
    client: httpx.AsyncClient = request.app.state.http
    url = f"/v1/{path}"
    body = await request.body()
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in {"host", "content-length", "transfer-encoding", "connection"}
    }
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
        return JSONResponse(
            status_code=502,
            content={
                "error": {
                    "code": "upstream_failure",
                    "message": "API upstream unreachable",
                    "retryable": True,
                    "correlation_id": request.headers.get("x-correlation-id", "unknown"),
                }
            },
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
