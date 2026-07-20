"""API: health and outbound message stub (enqueue to Redis DB 3)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Literal

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from omnimsg_common.ids import new_id
from omnimsg_common.queue import create_redis_client, enqueue_json
from omnimsg_common.settings import Settings, get_settings
from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)

app = FastAPI(title="OmniMsg API", version="0.1.0")


class TextBody(BaseModel):
    body: str = Field(min_length=1, max_length=4096)


class CreateMessageRequest(BaseModel):
    channel: Literal["whatsapp", "sms", "email", "rcs", "push"]
    to: str = Field(min_length=1, max_length=320)
    type: Literal["text"]
    text: TextBody | None = None
    metadata: dict[str, str] | None = None

    @model_validator(mode="after")
    def text_required_for_text_type(self) -> CreateMessageRequest:
        if self.type == "text" and self.text is None:
            raise ValueError("text is required when type is text")
        return self


class CreateMessageResponse(BaseModel):
    id: str
    status: Literal["queued"]
    channel: str
    created_at: str
    correlation_id: str


def _correlation_id(header_value: str | None) -> str:
    return header_value.strip() if header_value and header_value.strip() else new_id("req")


def _error(
    status_code: int,
    *,
    code: str,
    message: str,
    correlation_id: str,
    retryable: bool = False,
    details: list[dict[str, str]] | None = None,
) -> HTTPException:
    body: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
            "correlation_id": correlation_id,
        }
    }
    if details:
        body["error"]["details"] = details
    return HTTPException(status_code=status_code, detail=body)


@app.get("/v1/health")
async def health() -> dict[str, str]:
    settings = get_settings()
    return {"status": "ok", "version": settings.app_version}


@app.post("/v1/messages", status_code=202, response_model=CreateMessageResponse)
async def create_message(
    payload: CreateMessageRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
) -> CreateMessageResponse:
    """Accept a send command and enqueue it on Redis (foundation stub)."""
    settings: Settings = get_settings()
    correlation_id = _correlation_id(x_correlation_id)
    message_id = new_id("msg")
    now = datetime.now(UTC)
    created_at = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    queued_at = now.isoformat().replace("+00:00", "Z")

    event: dict[str, Any] = {
        "event_id": new_id("evt"),
        "event_type": "message.queued.v1",
        "occurred_at": queued_at,
        "tenant_id": settings.default_tenant_id,
        "correlation_id": correlation_id,
        "data": {
            "message_id": message_id,
            "channel": payload.channel,
            "to": payload.to,
            "queued_at": queued_at,
            "metadata": payload.metadata or {},
        },
    }
    job: dict[str, Any] = {
        "job_type": "outbound_message",
        "event": event,
        "payload": {
            "type": payload.type,
            "text": payload.text.model_dump() if payload.text else None,
            "idempotency_key": idempotency_key,
        },
    }

    try:
        client = create_redis_client(settings)
        enqueue_json(client, settings.outbound_queue_key, job)
        client.close()
    except Exception as exc:  # noqa: BLE001 — stub surfaces Redis failures as 502
        logger.exception("failed to enqueue message")
        raise _error(
            502,
            code="upstream_failure",
            message="Failed to enqueue message",
            correlation_id=correlation_id,
            retryable=True,
        ) from exc

    logger.info(
        "queued message_id=%s channel=%s correlation_id=%s",
        message_id,
        payload.channel,
        correlation_id,
    )

    return CreateMessageResponse(
        id=message_id,
        status="queued",
        channel=payload.channel,
        created_at=created_at,
        correlation_id=correlation_id,
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException):
    from fastapi.responses import JSONResponse

    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": "http_error",
                "message": str(exc.detail),
                "retryable": False,
                "correlation_id": new_id("req"),
            }
        },
    )


def run() -> None:
    logging.basicConfig(level=get_settings().log_level)
    uvicorn.run("omnimsg_api.main:app", host="0.0.0.0", port=8000, factory=False)


if __name__ == "__main__":
    run()
