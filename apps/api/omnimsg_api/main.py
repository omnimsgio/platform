"""API: auth resolve, message persist, idempotency, tenant-scoped reads."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Literal

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from omnimsg_common.auth import hash_api_key, looks_like_api_key
from omnimsg_common.db.models import ApiKey, Message, Tenant
from omnimsg_common.db.session import session_scope
from omnimsg_common.ids import new_id
from omnimsg_common.queue import create_redis_client, enqueue_json
from omnimsg_common.settings import Settings, get_settings
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

app = FastAPI(title="OmniMsg API", version="0.1.0")

TENANT_HEADER = "X-Tenant-Id"
API_KEY_ID_HEADER = "X-Api-Key-Id"


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


class MessageResponse(BaseModel):
    id: str
    status: str
    channel: str
    to: str
    type: str
    created_at: str
    updated_at: str
    correlation_id: str


class ResolveAuthRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=256)


class ResolveAuthResponse(BaseModel):
    tenant_id: str
    api_key_id: str


def _correlation_id(header_value: str | None) -> str:
    return header_value.strip() if header_value and header_value.strip() else new_id("req")


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _require_tenant(
    x_tenant_id: str | None,
    correlation_id: str,
) -> str:
    if not x_tenant_id or not x_tenant_id.strip():
        raise _error(
            401,
            code="unauthorized",
            message="Missing trusted tenant context",
            correlation_id=correlation_id,
        )
    return x_tenant_id.strip()


def _payload_fingerprint(payload: CreateMessageRequest) -> dict[str, Any]:
    return payload.model_dump(mode="json")


def _message_response_from_row(row: Message) -> CreateMessageResponse:
    return CreateMessageResponse(
        id=row.id,
        status="queued",
        channel=row.channel,
        created_at=_iso(row.created_at),
        correlation_id=row.correlation_id,
    )


@app.get("/v1/health")
async def health() -> dict[str, str]:
    settings = get_settings()
    return {"status": "ok", "version": settings.app_version}


@app.post("/internal/v1/auth/resolve", response_model=ResolveAuthResponse)
async def resolve_auth(body: ResolveAuthRequest) -> ResolveAuthResponse:
    """Resolve a Bearer API key to tenant context (Docker network only)."""
    raw = body.api_key.strip()
    if not looks_like_api_key(raw):
        raise _error(
            401,
            code="unauthorized",
            message="Invalid API key",
            correlation_id=new_id("req"),
        )

    digest = hash_api_key(raw)
    with session_scope() as session:
        row = session.scalars(
            select(ApiKey).where(
                ApiKey.key_hash == digest,
                ApiKey.status == "active",
            )
        ).first()
        if row is None:
            raise _error(
                401,
                code="unauthorized",
                message="Invalid API key",
                correlation_id=new_id("req"),
            )
        tenant = session.get(Tenant, row.tenant_id)
        if tenant is None or tenant.status != "active":
            raise _error(
                401,
                code="unauthorized",
                message="Tenant inactive",
                correlation_id=new_id("req"),
            )
        return ResolveAuthResponse(tenant_id=row.tenant_id, api_key_id=row.id)


@app.post("/v1/messages", status_code=202, response_model=CreateMessageResponse)
async def create_message(
    payload: CreateMessageRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    x_tenant_id: str | None = Header(default=None, alias=TENANT_HEADER),
    x_api_key_id: str | None = Header(default=None, alias=API_KEY_ID_HEADER),
) -> CreateMessageResponse:
    """Persist and enqueue an outbound message (tenant from gateway headers)."""
    settings: Settings = get_settings()
    correlation_id = _correlation_id(x_correlation_id)
    tenant_id = _require_tenant(x_tenant_id, correlation_id)
    del x_api_key_id  # accepted for tracing; not required for persist path

    key = idempotency_key.strip() if idempotency_key and idempotency_key.strip() else None
    fingerprint = _payload_fingerprint(payload)
    now = datetime.now(UTC)

    if key:
        with session_scope() as session:
            existing = session.scalars(
                select(Message).where(
                    Message.tenant_id == tenant_id,
                    Message.idempotency_key == key,
                )
            ).first()
            if existing is not None:
                stored = existing.payload or {}
                if stored.get("request") != fingerprint:
                    raise _error(
                        409,
                        code="conflict",
                        message="Idempotency key reused with a different payload",
                        correlation_id=correlation_id,
                    )
                return _message_response_from_row(existing)

    message_id = new_id("msg")
    queued_at = now.isoformat().replace("+00:00", "Z")
    row_payload = {
        "request": fingerprint,
        "text": payload.text.model_dump() if payload.text else None,
        "metadata": payload.metadata or {},
        "idempotency_key": key,
    }

    try:
        with session_scope() as session:
            if key:
                existing = session.scalars(
                    select(Message).where(
                        Message.tenant_id == tenant_id,
                        Message.idempotency_key == key,
                    )
                ).first()
                if existing is not None:
                    stored = existing.payload or {}
                    if stored.get("request") != fingerprint:
                        raise _error(
                            409,
                            code="conflict",
                            message="Idempotency key reused with a different payload",
                            correlation_id=correlation_id,
                        )
                    return _message_response_from_row(existing)

            row = Message(
                id=message_id,
                tenant_id=tenant_id,
                channel=payload.channel,
                to=payload.to,
                type=payload.type,
                status="queued",
                idempotency_key=key,
                correlation_id=correlation_id,
                payload=row_payload,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.flush()
            created_at = _iso(row.created_at)
    except IntegrityError as exc:
        # Concurrent insert with same idempotency key — replay if payload matches.
        if not key:
            raise _error(
                502,
                code="upstream_failure",
                message="Failed to persist message",
                correlation_id=correlation_id,
                retryable=True,
            ) from exc
        with session_scope() as session:
            existing = session.scalars(
                select(Message).where(
                    Message.tenant_id == tenant_id,
                    Message.idempotency_key == key,
                )
            ).first()
            if existing is None:
                raise _error(
                    502,
                    code="upstream_failure",
                    message="Failed to persist message",
                    correlation_id=correlation_id,
                    retryable=True,
                ) from exc
            stored = existing.payload or {}
            if stored.get("request") != fingerprint:
                raise _error(
                    409,
                    code="conflict",
                    message="Idempotency key reused with a different payload",
                    correlation_id=correlation_id,
                ) from exc
            return _message_response_from_row(existing)

    event: dict[str, Any] = {
        "event_id": new_id("evt"),
        "event_type": "message.queued.v1",
        "occurred_at": queued_at,
        "tenant_id": tenant_id,
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
            "idempotency_key": key,
        },
    }

    try:
        client = create_redis_client(settings)
        enqueue_json(client, settings.outbound_queue_key, job)
        client.close()
    except Exception as exc:  # noqa: BLE001 — surface Redis failures as 502
        logger.exception("failed to enqueue message")
        raise _error(
            502,
            code="upstream_failure",
            message="Failed to enqueue message",
            correlation_id=correlation_id,
            retryable=True,
        ) from exc

    logger.info(
        "queued message_id=%s channel=%s tenant_id=%s correlation_id=%s",
        message_id,
        payload.channel,
        tenant_id,
        correlation_id,
    )

    return CreateMessageResponse(
        id=message_id,
        status="queued",
        channel=payload.channel,
        created_at=created_at,
        correlation_id=correlation_id,
    )


@app.get("/v1/messages/{message_id}", response_model=MessageResponse)
async def get_message(
    message_id: str,
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    x_tenant_id: str | None = Header(default=None, alias=TENANT_HEADER),
) -> MessageResponse:
    """Return a tenant-scoped message by id."""
    correlation_id = _correlation_id(x_correlation_id)
    tenant_id = _require_tenant(x_tenant_id, correlation_id)

    with session_scope() as session:
        row = session.scalars(
            select(Message).where(
                Message.id == message_id,
                Message.tenant_id == tenant_id,
            )
        ).first()
        if row is None:
            raise _error(
                404,
                code="not_found",
                message="Message not found",
                correlation_id=correlation_id,
            )
        return MessageResponse(
            id=row.id,
            status=row.status,
            channel=row.channel,
            to=row.to,
            type=row.type,
            created_at=_iso(row.created_at),
            updated_at=_iso(row.updated_at),
            correlation_id=row.correlation_id,
        )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    correlation_id = _correlation_id(request.headers.get("x-correlation-id"))
    details: list[dict[str, str]] = []
    for err in exc.errors():
        loc = err.get("loc") or ()
        field = ".".join(str(part) for part in loc if part != "body")
        details.append(
            {
                "field": field or "body",
                "message": str(err.get("msg", "Invalid value")),
                "code": str(err.get("type", "validation_error")),
            }
        )
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": "validation_error",
                "message": "Request validation failed",
                "retryable": False,
                "correlation_id": correlation_id,
                "details": details,
            }
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException):
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
