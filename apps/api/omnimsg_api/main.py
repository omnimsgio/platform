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
from omnimsg_common.db.models import ApiKey, Conversation, Message, Tenant
from omnimsg_common.db.session import get_engine, session_scope
from omnimsg_common.ids import new_id
from omnimsg_common.queue import create_redis_client, enqueue_json
from omnimsg_common.settings import Settings, get_settings
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from omnimsg_api.embedded_signup import (
    EmbeddedSignupAttachError,
    EmbeddedSignupConfigError,
    EmbeddedSignupConflictError,
    EmbeddedSignupService,
)
from omnimsg_api.provisioning import (
    ProvisioningConflictError,
    ProvisioningRegisterError,
    ProvisioningService,
    ProvisioningStateError,
    ProvisioningUpstreamError,
)
from omnimsg_api.provisioning_retry import RetryService
from omnimsg_api.whatsapp_health import HealthService

logger = logging.getLogger(__name__)

app = FastAPI(
    title="OmniMsg API",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

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
    direction: str = "outbound"
    from_address: str | None = None
    conversation_id: str | None = None
    provider_message_id: str | None = None


class ConversationMessagesResponse(BaseModel):
    conversation_id: str
    messages: list[MessageResponse]
    limit: int
    offset: int


class ResolveAuthRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=256)


class ResolveAuthResponse(BaseModel):
    tenant_id: str
    api_key_id: str


class EmbeddedSignupCompleteRequest(BaseModel):
    code: str = Field(min_length=1, max_length=4096)
    waba_id: str = Field(min_length=1, max_length=64)
    phone_number_id: str = Field(min_length=1, max_length=64)
    meta_business_id: str | None = Field(default=None, max_length=64)


class EmbeddedSignupCompleteResponse(BaseModel):
    account_id: str
    tenant_id: str
    waba_id: str
    phone_number_id: str
    status: str
    already_attached: bool
    correlation_id: str
    meta_business_id: str | None = None
    status_reason: str | None = None


class EmbeddedSignupStartResponse(BaseModel):
    account_id: str
    tenant_id: str
    status: str
    correlation_id: str
    already_started: bool


class HealthChecks(BaseModel):
    business_token: bool
    waba: bool
    phone_number: bool
    phone_registered: bool
    webhook_verified: bool
    graph_health: bool


class WhatsappConnectionResponse(BaseModel):
    status: str
    status_reason: str | None = None
    updated_at: str | None = None
    correlation_id: str | None = None
    last_error: str | None = None
    recovery_target: str | None = None
    lifecycle_version: int
    waba_id: str | None = None
    phone_number_id: str | None = None
    credit_line_attached: bool
    badge: str
    message: str
    account_id: str | None = None
    checks: HealthChecks | None = None


class RegisterPhoneRequest(BaseModel):
    pin: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class RegisterPhoneResponse(BaseModel):
    status: str
    status_reason: str | None = None
    updated_at: str | None = None
    correlation_id: str
    already_registered: bool
    last_error: str | None = None
    recovery_target: str | None = None
    lifecycle_version: int
    waba_id: str | None = None
    phone_number_id: str | None = None
    credit_line_attached: bool
    badge: str
    message: str
    account_id: str | None = None


class ProvisionWebhookResponse(BaseModel):
    status: str
    status_reason: str | None = None
    updated_at: str | None = None
    correlation_id: str
    already_provisioned: bool
    last_error: str | None = None
    recovery_target: str | None = None
    lifecycle_version: int
    waba_id: str | None = None
    phone_number_id: str | None = None
    credit_line_attached: bool
    badge: str
    message: str
    account_id: str | None = None


class HealthCheckResponse(BaseModel):
    status: str
    status_reason: str | None = None
    updated_at: str | None = None
    correlation_id: str
    already_healthy: bool
    checks: HealthChecks
    last_error: str | None = None
    recovery_target: str | None = None
    lifecycle_version: int
    waba_id: str | None = None
    phone_number_id: str | None = None
    credit_line_attached: bool
    badge: str
    message: str
    account_id: str | None = None


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


def _full_message_response(row: Message) -> MessageResponse:
    return MessageResponse(
        id=row.id,
        status=row.status,
        channel=row.channel,
        to=row.to,
        type=row.type,
        created_at=_iso(row.created_at),
        updated_at=_iso(row.updated_at),
        correlation_id=row.correlation_id,
        direction=getattr(row, "direction", None) or "outbound",
        from_address=getattr(row, "from_address", None),
        conversation_id=getattr(row, "conversation_id", None),
        provider_message_id=getattr(row, "provider_message_id", None),
    )


class ReadinessChecks(BaseModel):
    database: bool
    redis: bool
    worker: bool | None = None
    provider: bool | None = None


class ApiHealthResponse(BaseModel):
    status: Literal["ok", "degraded", "error"]
    version: str
    checks: ReadinessChecks


@app.get("/v1/health", response_model=ApiHealthResponse)
async def health() -> JSONResponse:
    """API readiness: database + redis required (ADR-0021)."""
    settings = get_settings()
    database_ok = False
    redis_ok = False
    try:
        with get_engine(settings).connect() as conn:
            conn.execute(text("SELECT 1"))
        database_ok = True
    except Exception:  # noqa: BLE001 — readiness must not raise
        logger.warning("v1 health database check failed", exc_info=True)

    try:
        client = create_redis_client(settings)
        try:
            redis_ok = bool(client.ping())
        finally:
            client.close()
    except Exception:  # noqa: BLE001
        logger.warning("v1 health redis check failed", exc_info=True)

    checks = ReadinessChecks(
        database=database_ok,
        redis=redis_ok,
        worker=None,
        provider=None,
    )
    if database_ok and redis_ok:
        status: Literal["ok", "degraded", "error"] = "ok"
        code = 200
    else:
        status = "error"
        code = 503
    body = ApiHealthResponse(
        status=status,
        version=settings.app_version,
        checks=checks,
    )
    return JSONResponse(status_code=code, content=body.model_dump(mode="json"))


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
        return _full_message_response(row)


@app.get(
    "/v1/conversations/{conversation_id}/messages",
    response_model=ConversationMessagesResponse,
)
async def list_conversation_messages(
    conversation_id: str,
    limit: int = 50,
    offset: int = 0,
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    x_tenant_id: str | None = Header(default=None, alias=TENANT_HEADER),
) -> ConversationMessagesResponse:
    """List messages in a conversation thread (oldest → newest). Read-only in P3."""
    correlation_id = _correlation_id(x_correlation_id)
    tenant_id = _require_tenant(x_tenant_id, correlation_id)
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    with session_scope() as session:
        conversation = session.scalars(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.tenant_id == tenant_id,
            )
        ).first()
        if conversation is None:
            raise _error(
                404,
                code="not_found",
                message="Conversation not found",
                correlation_id=correlation_id,
            )
        rows = session.scalars(
            select(Message)
            .where(
                Message.tenant_id == tenant_id,
                Message.conversation_id == conversation_id,
            )
            .order_by(Message.created_at.asc())
            .offset(offset)
            .limit(limit)
        ).all()
        return ConversationMessagesResponse(
            conversation_id=conversation_id,
            messages=[_full_message_response(row) for row in rows],
            limit=limit,
            offset=offset,
        )


@app.post(
    "/v1/whatsapp/embedded-signup/start",
    response_model=EmbeddedSignupStartResponse,
)
async def start_embedded_signup(
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    x_tenant_id: str | None = Header(default=None, alias=TENANT_HEADER),
) -> EmbeddedSignupStartResponse:
    """Mark WhatsApp connection lifecycle as Embedded Signup started."""
    settings = get_settings()
    correlation_id = _correlation_id(x_correlation_id)
    tenant_id = _require_tenant(x_tenant_id, correlation_id)
    result = EmbeddedSignupService(settings).start_signup(
        tenant_id=tenant_id,
        correlation_id=correlation_id,
    )
    return EmbeddedSignupStartResponse(
        account_id=result.account_id,
        tenant_id=result.tenant_id,
        status=result.status,
        correlation_id=result.correlation_id,
        already_started=result.already_started,
    )


@app.get(
    "/v1/whatsapp/connection",
    response_model=WhatsappConnectionResponse,
)
async def get_whatsapp_connection(
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    x_tenant_id: str | None = Header(default=None, alias=TENANT_HEADER),
) -> WhatsappConnectionResponse:
    """Return canonical WhatsApp connection lifecycle for the tenant."""
    settings = get_settings()
    correlation_id = _correlation_id(x_correlation_id)
    tenant_id = _require_tenant(x_tenant_id, correlation_id)
    view = EmbeddedSignupService(settings).get_connection(tenant_id=tenant_id)
    return WhatsappConnectionResponse(
        status=view.status,
        status_reason=view.status_reason,
        updated_at=_iso(view.updated_at) if view.updated_at else None,
        correlation_id=view.correlation_id,
        last_error=view.last_error,
        recovery_target=view.recovery_target,
        lifecycle_version=view.lifecycle_version,
        waba_id=view.waba_id,
        phone_number_id=view.phone_number_id,
        credit_line_attached=view.credit_line_attached,
        badge=view.badge,
        message=view.message,
        account_id=view.account_id,
    )


@app.post(
    "/v1/whatsapp/register-phone",
    response_model=RegisterPhoneResponse,
)
async def register_whatsapp_phone(
    payload: RegisterPhoneRequest,
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    x_tenant_id: str | None = Header(default=None, alias=TENANT_HEADER),
) -> RegisterPhoneResponse:
    """Register Cloud API phone (PIN) and advance lifecycle to WEBHOOK_PENDING."""
    settings = get_settings()
    correlation_id = _correlation_id(x_correlation_id)
    tenant_id = _require_tenant(x_tenant_id, correlation_id)
    try:
        result = ProvisioningService(settings).register_phone(
            tenant_id=tenant_id,
            pin=payload.pin,
            correlation_id=correlation_id,
        )
    except ProvisioningConflictError as exc:
        raise _error(
            409,
            code="conflict",
            message=str(exc),
            correlation_id=exc.correlation_id,
        ) from exc
    except ProvisioningStateError as exc:
        raise _error(
            409,
            code="conflict",
            message=str(exc),
            correlation_id=exc.correlation_id,
        ) from exc
    except ProvisioningRegisterError as exc:
        raise _error(
            502,
            code="upstream_failure",
            message=str(exc),
            correlation_id=exc.correlation_id,
            retryable=True,
        ) from exc

    return RegisterPhoneResponse(
        status=result.status,
        status_reason=result.status_reason,
        updated_at=_iso(result.updated_at) if result.updated_at else None,
        correlation_id=result.correlation_id,
        already_registered=result.already_registered,
        last_error=result.last_error,
        recovery_target=result.recovery_target,
        lifecycle_version=result.lifecycle_version,
        waba_id=result.waba_id,
        phone_number_id=result.phone_number_id,
        credit_line_attached=result.credit_line_attached,
        badge=result.badge,
        message=result.message,
        account_id=result.account_id,
    )


@app.post(
    "/v1/whatsapp/provision-webhook",
    response_model=ProvisionWebhookResponse,
)
async def provision_whatsapp_webhook(
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    x_tenant_id: str | None = Header(default=None, alias=TENANT_HEADER),
) -> ProvisionWebhookResponse:
    """Subscribe WABA to app webhooks (Graph) and advance to HEALTH_CHECK_PENDING.

    App-level hub verify (GET challenge) stays on the gateway; this endpoint only
    performs tenant-level subscribed_apps subscribe + Graph confirmation.
    """
    settings = get_settings()
    correlation_id = _correlation_id(x_correlation_id)
    tenant_id = _require_tenant(x_tenant_id, correlation_id)
    try:
        result = ProvisioningService(settings).provision_webhook(
            tenant_id=tenant_id,
            correlation_id=correlation_id,
        )
    except ProvisioningConflictError as exc:
        raise _error(
            409,
            code="conflict",
            message=str(exc),
            correlation_id=exc.correlation_id,
        ) from exc
    except ProvisioningStateError as exc:
        raise _error(
            409,
            code="conflict",
            message=str(exc),
            correlation_id=exc.correlation_id,
        ) from exc
    except ProvisioningUpstreamError as exc:
        raise _error(
            502,
            code="upstream_failure",
            message=str(exc),
            correlation_id=exc.correlation_id,
            retryable=True,
        ) from exc

    return ProvisionWebhookResponse(
        status=result.status,
        status_reason=result.status_reason,
        updated_at=_iso(result.updated_at) if result.updated_at else None,
        correlation_id=result.correlation_id,
        already_provisioned=result.already_provisioned,
        last_error=result.last_error,
        recovery_target=result.recovery_target,
        lifecycle_version=result.lifecycle_version,
        waba_id=result.waba_id,
        phone_number_id=result.phone_number_id,
        credit_line_attached=result.credit_line_attached,
        badge=result.badge,
        message=result.message,
        account_id=result.account_id,
    )


@app.post(
    "/v1/whatsapp/health-check",
    response_model=HealthCheckResponse,
)
async def whatsapp_health_check(
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    x_tenant_id: str | None = Header(default=None, alias=TENANT_HEADER),
) -> HealthCheckResponse:
    """Run ADR-0020 health_ok checks; single transition to READY or ERROR."""
    settings = get_settings()
    correlation_id = _correlation_id(x_correlation_id)
    tenant_id = _require_tenant(x_tenant_id, correlation_id)
    try:
        result = HealthService(settings).check_and_promote(
            tenant_id=tenant_id,
            correlation_id=correlation_id,
        )
    except ProvisioningConflictError as exc:
        raise _error(
            409,
            code="conflict",
            message=str(exc),
            correlation_id=exc.correlation_id,
        ) from exc
    except ProvisioningStateError as exc:
        raise _error(
            409,
            code="conflict",
            message=str(exc),
            correlation_id=exc.correlation_id,
        ) from exc

    return HealthCheckResponse(
        status=result.status,
        status_reason=result.status_reason,
        updated_at=_iso(result.updated_at) if result.updated_at else None,
        correlation_id=result.correlation_id,
        already_healthy=result.already_healthy,
        checks=HealthChecks(**result.checks),
        last_error=result.last_error,
        recovery_target=result.recovery_target,
        lifecycle_version=result.lifecycle_version,
        waba_id=result.waba_id,
        phone_number_id=result.phone_number_id,
        credit_line_attached=result.credit_line_attached,
        badge=result.badge,
        message=result.message,
        account_id=result.account_id,
    )


@app.post(
    "/v1/whatsapp/retry",
    response_model=WhatsappConnectionResponse,
)
async def retry_whatsapp_provisioning(
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    x_tenant_id: str | None = Header(default=None, alias=TENANT_HEADER),
) -> WhatsappConnectionResponse:
    """Recover from ERROR via recovery_target only (ADR-0020). Same shape as GET connection."""
    settings = get_settings()
    correlation_id = _correlation_id(x_correlation_id)
    tenant_id = _require_tenant(x_tenant_id, correlation_id)
    try:
        result = RetryService(settings).retry(
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            retry_reason="user",
        )
    except ProvisioningConflictError as exc:
        raise _error(
            409,
            code="conflict",
            message=str(exc),
            correlation_id=exc.correlation_id,
        ) from exc
    except ProvisioningStateError as exc:
        raise _error(
            409,
            code="conflict",
            message=str(exc),
            correlation_id=exc.correlation_id,
        ) from exc
    except ProvisioningUpstreamError as exc:
        raise _error(
            502,
            code="upstream_failure",
            message=str(exc),
            correlation_id=exc.correlation_id,
            retryable=True,
        ) from exc

    return WhatsappConnectionResponse(
        status=result.status,
        status_reason=result.status_reason,
        updated_at=_iso(result.updated_at) if result.updated_at else None,
        correlation_id=result.correlation_id,
        last_error=result.last_error,
        recovery_target=result.recovery_target,
        lifecycle_version=result.lifecycle_version,
        waba_id=result.waba_id,
        phone_number_id=result.phone_number_id,
        credit_line_attached=result.credit_line_attached,
        badge=result.badge,
        message=result.message,
        account_id=result.account_id,
        checks=HealthChecks(**result.checks) if result.checks is not None else None,
    )


@app.post(
    "/v1/whatsapp/embedded-signup/complete",
    response_model=EmbeddedSignupCompleteResponse,
)
async def complete_embedded_signup(
    payload: EmbeddedSignupCompleteRequest,
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    x_tenant_id: str | None = Header(default=None, alias=TENANT_HEADER),
    x_api_key_id: str | None = Header(default=None, alias=API_KEY_ID_HEADER),
) -> EmbeddedSignupCompleteResponse:
    """Exchange ES auth code and attach WhatsApp phone to the authenticated tenant."""
    settings = get_settings()
    correlation_id = _correlation_id(x_correlation_id)
    tenant_id = _require_tenant(x_tenant_id, correlation_id)
    api_key_id = x_api_key_id.strip() if x_api_key_id and x_api_key_id.strip() else None

    service = EmbeddedSignupService(settings)
    try:
        result = service.attach_tenant_phone(
            tenant_id=tenant_id,
            api_key_id=api_key_id,
            code=payload.code,
            waba_id=payload.waba_id,
            phone_number_id=payload.phone_number_id,
            meta_business_id=payload.meta_business_id,
            correlation_id=correlation_id,
        )
    except EmbeddedSignupConflictError as exc:
        raise _error(
            409,
            code="conflict",
            message=str(exc),
            correlation_id=exc.correlation_id,
        ) from exc
    except EmbeddedSignupConfigError as exc:
        raise _error(
            503,
            code="upstream_failure",
            message=str(exc),
            correlation_id=exc.correlation_id,
            retryable=False,
        ) from exc
    except EmbeddedSignupAttachError as exc:
        raise _error(
            502,
            code="upstream_failure",
            message=str(exc),
            correlation_id=exc.correlation_id,
            retryable=True,
        ) from exc

    return EmbeddedSignupCompleteResponse(
        account_id=result.account_id,
        tenant_id=result.tenant_id,
        waba_id=result.waba_id,
        phone_number_id=result.phone_number_id,
        status=result.status,
        already_attached=result.already_attached,
        correlation_id=result.correlation_id,
        meta_business_id=result.meta_business_id,
        status_reason=result.status_reason,
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
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    dsn = (settings.sentry_dsn or "").strip()
    if dsn:
        try:
            import sentry_sdk

            sentry_sdk.init(dsn=dsn, traces_sample_rate=0.0)
            logger.info("sentry initialized")
        except Exception:
            logger.exception("sentry init failed")
    uvicorn.run("omnimsg_api.main:app", host="0.0.0.0", port=8000, factory=False)


if __name__ == "__main__":
    run()
