"""Partner onboarding invites — bootstrap Tenant + API key (no SQLAdmin ModelView)."""

from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse
from omnimsg_common.auth import generate_api_key, hash_api_key, key_display_prefix
from omnimsg_common.db.models import ApiKey, PartnerInvite, Tenant
from omnimsg_common.db.session import session_scope
from omnimsg_common.ids import new_id
from omnimsg_common.settings import get_settings
from pydantic import BaseModel, Field
from sqlalchemy import select

from omnimsg_api.admin import record_admin_audit, verify_admin_basic

logger = logging.getLogger(__name__)

STATUS_PENDING = "pending"
STATUS_ACCEPTED = "accepted"
STATUS_EXPIRED = "expired"
STATUS_REVOKED = "revoked"

INVITE_TOKEN_PREFIX = "inv_"


class InviteCreateError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class InviteAcceptError(Exception):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class CreatedInvite:
    invite_id: str
    raw_token: str
    onboard_url: str
    expires_at: datetime
    partner_name: str
    partner_email: str | None


@dataclass(frozen=True)
class AcceptedInvite:
    invite_id: str
    tenant_id: str
    api_key_id: str
    api_key: str
    partner_name: str


def hash_invite_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_invite_token() -> str:
    return f"{INVITE_TOKEN_PREFIX}{secrets.token_urlsafe(32)}"


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _onboard_url(raw_token: str) -> str:
    base = get_settings().portal_base_url.rstrip("/")
    return f"{base}/onboard/{raw_token}"


def _audit(
    *,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: str | None,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    correlation_id: str,
    request_ip: str | None,
    user_agent: str | None,
) -> None:
    record_admin_audit(
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
        correlation_id=correlation_id,
        request_id=correlation_id,
        request_ip=request_ip,
        user_agent=user_agent,
    )


def create_invite(
    *,
    actor: str,
    partner_name: str,
    partner_email: str | None,
    ttl_hours: int | None,
    correlation_id: str,
    request_ip: str | None = None,
    user_agent: str | None = None,
) -> CreatedInvite:
    name = partner_name.strip()
    if not name:
        raise InviteCreateError("invalid_partner_name", "partner_name is required")
    email = partner_email.strip() if partner_email else None
    if email == "":
        email = None
    settings = get_settings()
    hours = ttl_hours if ttl_hours is not None else settings.partner_invite_ttl_hours
    if hours < 1 or hours > 720:
        raise InviteCreateError("invalid_ttl", "ttl_hours must be between 1 and 720")

    raw = generate_invite_token()
    invite_id = new_id("inv")
    expires_at = _utcnow() + timedelta(hours=hours)
    with session_scope() as session:
        session.add(
            PartnerInvite(
                id=invite_id,
                token_hash=hash_invite_token(raw),
                token_prefix=raw[:12],
                partner_name=name,
                partner_email=email,
                status=STATUS_PENDING,
                expires_at=expires_at,
                created_by_actor=actor,
            )
        )

    _audit(
        actor=actor,
        action="invite_created",
        entity_type="partner_invite",
        entity_id=invite_id,
        before=None,
        after={
            "partner_name": name,
            "partner_email": email,
            "expires_at": expires_at.isoformat(),
            "token_prefix": raw[:12],
        },
        correlation_id=correlation_id,
        request_ip=request_ip,
        user_agent=user_agent,
    )
    logger.info(
        "PartnerInviteCreated invite_id=%s actor=%s correlation_id=%s",
        invite_id,
        actor,
        correlation_id,
    )
    return CreatedInvite(
        invite_id=invite_id,
        raw_token=raw,
        onboard_url=_onboard_url(raw),
        expires_at=expires_at,
        partner_name=name,
        partner_email=email,
    )


def accept_invite(
    *,
    raw_token: str,
    correlation_id: str,
    request_ip: str | None = None,
    user_agent: str | None = None,
) -> AcceptedInvite:
    token = (raw_token or "").strip()
    if not token.startswith(INVITE_TOKEN_PREFIX):
        raise InviteAcceptError(
            "invite_not_found",
            "Invite token is invalid",
            404,
        )
    token_hash = hash_invite_token(token)
    now = _utcnow()

    with session_scope() as session:
        row = session.scalar(
            select(PartnerInvite)
            .where(PartnerInvite.token_hash == token_hash)
            .with_for_update()
        )
        if row is None:
            raise InviteAcceptError(
                "invite_not_found",
                "Invite token is invalid",
                404,
            )
        if row.status == STATUS_ACCEPTED:
            raise InviteAcceptError(
                "invite_already_accepted",
                "Invite already accepted",
                410,
            )
        if row.status == STATUS_REVOKED:
            raise InviteAcceptError(
                "invite_revoked",
                "Invite has been revoked",
                410,
            )
        if row.status == STATUS_EXPIRED or row.expires_at <= now:
            if row.status == STATUS_PENDING:
                row.status = STATUS_EXPIRED
            raise InviteAcceptError(
                "invite_expired",
                "Invite has expired",
                410,
            )
        if row.status != STATUS_PENDING:
            raise InviteAcceptError(
                "invite_not_pending",
                "Invite is not available for accept",
                410,
            )

        # Second concurrent waiter that lost the race after first commit would
        # see accepted; within this lock we are sole writer for this row.
        tenant_id = new_id("ten")
        api_key_id = new_id("key")
        raw_key = generate_api_key()
        session.add(
            Tenant(id=tenant_id, name=row.partner_name, status="active")
        )
        session.add(
            ApiKey(
                id=api_key_id,
                tenant_id=tenant_id,
                key_prefix=key_display_prefix(raw_key),
                key_hash=hash_api_key(raw_key),
                status="active",
            )
        )
        session.flush()
        row.status = STATUS_ACCEPTED
        row.accepted_at = now
        row.tenant_id = tenant_id
        row.api_key_id = api_key_id
        invite_id = row.id
        partner_name = row.partner_name

    actor = f"invite:{invite_id}"
    _audit(
        actor=actor,
        action="invite_accepted",
        entity_type="partner_invite",
        entity_id=invite_id,
        before={"status": STATUS_PENDING},
        after={"status": STATUS_ACCEPTED, "tenant_id": tenant_id},
        correlation_id=correlation_id,
        request_ip=request_ip,
        user_agent=user_agent,
    )
    _audit(
        actor=actor,
        action="tenant_created",
        entity_type="tenant",
        entity_id=tenant_id,
        before=None,
        after={"name": partner_name, "status": "active", "source": "partner_invite"},
        correlation_id=correlation_id,
        request_ip=request_ip,
        user_agent=user_agent,
    )
    _audit(
        actor=actor,
        action="apikey_created",
        entity_type="api_key",
        entity_id=api_key_id,
        before=None,
        after={
            "tenant_id": tenant_id,
            "key_prefix": key_display_prefix(raw_key),
            "source": "partner_invite",
        },
        correlation_id=correlation_id,
        request_ip=request_ip,
        user_agent=user_agent,
    )
    logger.info(
        "PartnerInviteAccepted invite_id=%s tenant_id=%s correlation_id=%s",
        invite_id,
        tenant_id,
        correlation_id,
    )
    return AcceptedInvite(
        invite_id=invite_id,
        tenant_id=tenant_id,
        api_key_id=api_key_id,
        api_key=raw_key,
        partner_name=partner_name,
    )


def get_invite(invite_id: str) -> PartnerInvite | None:
    with session_scope() as session:
        row = session.get(PartnerInvite, invite_id)
        if row is None:
            return None
        session.expunge(row)
        return row


def revoke_invite(
    *,
    invite_id: str,
    actor: str,
    correlation_id: str,
    request_ip: str | None = None,
    user_agent: str | None = None,
) -> dict[str, str]:
    with session_scope() as session:
        row = session.get(PartnerInvite, invite_id)
        if row is None:
            raise InviteCreateError("invite_not_found", "Invite not found", 404)
        if row.status == STATUS_ACCEPTED:
            raise InviteCreateError(
                "invite_already_accepted",
                "Accepted invites cannot be revoked",
                409,
            )
        if row.status == STATUS_REVOKED:
            return {"id": row.id, "status": row.status}
        before = {"status": row.status}
        row.status = STATUS_REVOKED
        result = {"id": row.id, "status": row.status}

    _audit(
        actor=actor,
        action="invite_revoked",
        entity_type="partner_invite",
        entity_id=invite_id,
        before=before,
        after={"status": STATUS_REVOKED},
        correlation_id=correlation_id,
        request_ip=request_ip,
        user_agent=user_agent,
    )
    return result


# --- HTTP layer ---


class CreateInviteBody(BaseModel):
    partner_name: str = Field(min_length=1, max_length=255)
    partner_email: str | None = Field(default=None, max_length=320)
    ttl_hours: int | None = Field(default=None, ge=1, le=720)


class AcceptInviteBody(BaseModel):
    token: str = Field(min_length=8, max_length=256)


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def _error_json(
    status_code: int,
    *,
    code: str,
    message: str,
    correlation_id: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "retryable": False,
                "correlation_id": correlation_id,
            }
        },
        headers={"X-Correlation-Id": correlation_id},
    )


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def mount_partner_invite_routes(app: FastAPI) -> None:
    """Register admin + public invite routes (call before SQLAdmin mount)."""

    @app.post("/admin/partner-invites", include_in_schema=False)
    async def admin_create_invite(
        request: Request,
        body: CreateInviteBody,
        x_correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    ) -> JSONResponse:
        correlation_id = x_correlation_id or new_id("req")
        settings = get_settings()
        actor = verify_admin_basic(request.headers.get("authorization"), settings)
        if not actor:
            return _error_json(
                401,
                code="unauthorized",
                message="Admin Basic auth required",
                correlation_id=correlation_id,
            )
        try:
            created = create_invite(
                actor=actor,
                partner_name=body.partner_name,
                partner_email=str(body.partner_email) if body.partner_email else None,
                ttl_hours=body.ttl_hours,
                correlation_id=correlation_id,
                request_ip=_client_ip(request),
                user_agent=request.headers.get("user-agent"),
            )
        except InviteCreateError as exc:
            return _error_json(
                exc.status_code,
                code=exc.code,
                message=exc.message,
                correlation_id=correlation_id,
            )
        return JSONResponse(
            status_code=201,
            content={
                "id": created.invite_id,
                "onboard_url": created.onboard_url,
                "token": created.raw_token,
                "partner_name": created.partner_name,
                "partner_email": created.partner_email,
                "expires_at": _iso(created.expires_at),
                "status": STATUS_PENDING,
            },
            headers={"X-Correlation-Id": correlation_id},
        )

    @app.get("/admin/partner-invites/{invite_id}", include_in_schema=False)
    async def admin_get_invite(
        request: Request,
        invite_id: str,
        x_correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    ) -> JSONResponse:
        correlation_id = x_correlation_id or new_id("req")
        settings = get_settings()
        actor = verify_admin_basic(request.headers.get("authorization"), settings)
        if not actor:
            return _error_json(
                401,
                code="unauthorized",
                message="Admin Basic auth required",
                correlation_id=correlation_id,
            )
        row = get_invite(invite_id)
        if row is None:
            return _error_json(
                404,
                code="invite_not_found",
                message="Invite not found",
                correlation_id=correlation_id,
            )
        return JSONResponse(
            content={
                "id": row.id,
                "status": row.status,
                "partner_name": row.partner_name,
                "partner_email": row.partner_email,
                "token_prefix": row.token_prefix,
                "expires_at": _iso(row.expires_at),
                "accepted_at": _iso(row.accepted_at) if row.accepted_at else None,
                "tenant_id": row.tenant_id,
                "api_key_id": row.api_key_id,
                "created_by_actor": row.created_by_actor,
                "created_at": _iso(row.created_at),
            },
            headers={"X-Correlation-Id": correlation_id},
        )

    @app.post("/admin/partner-invites/{invite_id}/revoke", include_in_schema=False)
    async def admin_revoke_invite(
        request: Request,
        invite_id: str,
        x_correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    ) -> JSONResponse:
        correlation_id = x_correlation_id or new_id("req")
        settings = get_settings()
        actor = verify_admin_basic(request.headers.get("authorization"), settings)
        if not actor:
            return _error_json(
                401,
                code="unauthorized",
                message="Admin Basic auth required",
                correlation_id=correlation_id,
            )
        try:
            result = revoke_invite(
                invite_id=invite_id,
                actor=actor,
                correlation_id=correlation_id,
                request_ip=_client_ip(request),
                user_agent=request.headers.get("user-agent"),
            )
        except InviteCreateError as exc:
            return _error_json(
                exc.status_code,
                code=exc.code,
                message=exc.message,
                correlation_id=correlation_id,
            )
        return JSONResponse(
            content=result,
            headers={"X-Correlation-Id": correlation_id},
        )

    @app.post("/v1/partner-invites/accept")
    async def public_accept_invite(
        request: Request,
        body: AcceptInviteBody,
        x_correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    ) -> JSONResponse:
        correlation_id = x_correlation_id or new_id("req")
        try:
            accepted = accept_invite(
                raw_token=body.token,
                correlation_id=correlation_id,
                request_ip=_client_ip(request),
                user_agent=request.headers.get("user-agent"),
            )
        except InviteAcceptError as exc:
            return _error_json(
                exc.status_code,
                code=exc.code,
                message=exc.message,
                correlation_id=correlation_id,
            )
        return JSONResponse(
            content={
                "invite_id": accepted.invite_id,
                "tenant_id": accepted.tenant_id,
                "api_key_id": accepted.api_key_id,
                "api_key": accepted.api_key,
                "partner_name": accepted.partner_name,
            },
            headers={"X-Correlation-Id": correlation_id},
        )
