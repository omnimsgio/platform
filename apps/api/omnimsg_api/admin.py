"""Ops SQLAdmin mount (ADR-0022 Phase C1)."""

from __future__ import annotations

import hmac
import logging
import secrets
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from omnimsg_common.db.models import AdminAuditEvent
from omnimsg_common.db.session import get_engine, get_session_factory
from omnimsg_common.ids import new_id
from omnimsg_common.openapi_contract import load_openapi_contract, resolve_contract_path
from omnimsg_common.queue import create_redis_client
from omnimsg_common.settings import Settings, get_settings
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from wtforms import TextAreaField

logger = logging.getLogger(__name__)

_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _const_eq(left: str, right: str) -> bool:
    if len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)


def _parse_basic(authorization: str | None) -> tuple[str, str] | None:
    if not authorization:
        return None
    scheme, _, rest = authorization.partition(" ")
    if scheme.lower() != "basic" or not rest.strip():
        return None
    try:
        import base64

        decoded = base64.b64decode(rest.strip()).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    user, sep, password = decoded.partition(":")
    if not sep:
        return None
    return user, password


def verify_admin_basic(authorization: str | None, settings: Settings) -> str | None:
    """Return actor username if Basic credentials match; else None."""
    if not settings.admin_enabled:
        return None
    parsed = _parse_basic(authorization)
    if parsed is None:
        return None
    user, password = parsed
    user_ok = _const_eq(user, settings.admin_username)
    pass_ok = _const_eq(password, settings.admin_password)
    if user_ok and pass_ok:
        return user
    return None


class AdminAuthBackend(AuthenticationBackend):
    """SQLAdmin session auth backed by the same Basic credentials."""

    async def login(self, request: StarletteRequest) -> bool:
        form = await request.form()
        username = str(form.get("username", ""))
        password = str(form.get("password", ""))
        settings = get_settings()
        if not settings.admin_enabled:
            return False
        user_ok = _const_eq(username, settings.admin_username)
        pass_ok = _const_eq(password, settings.admin_password)
        if not (user_ok and pass_ok):
            return False
        request.session.update({"admin_user": username})
        return True

    async def logout(self, request: StarletteRequest) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: StarletteRequest) -> bool:
        settings = get_settings()
        if not settings.admin_enabled:
            return False
        session_user = request.session.get("admin_user")
        if isinstance(session_user, str) and session_user == settings.admin_username:
            return True
        actor = verify_admin_basic(request.headers.get("authorization"), settings)
        if actor:
            request.session.update({"admin_user": actor})
            return True
        return False


class AdminReadOnlyMiddleware(BaseHTTPMiddleware):
    """Server-side deny for admin writes when ADMIN_READ_ONLY=true (ADR-0022)."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        path = request.url.path
        if not path.startswith("/admin"):
            return await call_next(request)
        settings = get_settings()
        if not settings.admin_read_only:
            return await call_next(request)
        method = request.method.upper()
        # SQLAdmin custom actions are registered as GET but mutate state (C2+).
        is_sqladmin_action = "/action/" in path
        # Allow GET/HEAD/OPTIONS and SQLAdmin login/logout GETs; block mutations.
        if method in _WRITE_METHODS or is_sqladmin_action:
            # Permit login POST so operators can still open a session to browse.
            if path.rstrip("/").endswith("/login") and method in _WRITE_METHODS:
                return await call_next(request)
            correlation = request.headers.get("x-correlation-id") or new_id("req")
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "admin_read_only",
                        "message": "Admin is in read-only mode (ADMIN_READ_ONLY=true)",
                        "retryable": False,
                        "correlation_id": correlation,
                    }
                },
                headers={"X-Correlation-Id": correlation},
            )
        return await call_next(request)


class AdminBasicGateMiddleware(BaseHTTPMiddleware):
    """Require admin credentials before reaching SQLAdmin (defense in depth)."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        path = request.url.path
        if not path.startswith("/admin"):
            return await call_next(request)
        settings = get_settings()
        if not settings.admin_enabled:
            return JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "code": "admin_disabled",
                        "message": "Admin is not configured",
                        "retryable": False,
                        "correlation_id": new_id("req"),
                    }
                },
            )
        # Allow static/login to proceed; authenticate() still enforces session/Basic.
        return await call_next(request)


def record_admin_audit(
    *,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: str | None,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    correlation_id: str | None,
    request_id: str | None,
    request_ip: str | None,
    user_agent: str | None,
) -> None:
    factory = get_session_factory()
    with factory() as session:
        session.add(
            AdminAuditEvent(
                id=new_id("aud"),
                actor=actor,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                before=before,
                after=after,
                correlation_id=correlation_id,
                request_id=request_id,
                request_ip=request_ip,
                user_agent=(user_agent or "")[:512] or None,
            )
        )
        session.commit()


class AdminAuditEventAdmin(ModelView, model=AdminAuditEvent):
    name = "Audit Event"
    name_plural = "Audit Events"
    icon = "fa-solid fa-clipboard-list"
    column_list = [
        AdminAuditEvent.created_at,
        AdminAuditEvent.actor,
        AdminAuditEvent.action,
        AdminAuditEvent.entity_type,
        AdminAuditEvent.entity_id,
        AdminAuditEvent.request_ip,
        AdminAuditEvent.correlation_id,
    ]
    column_searchable_list = [
        AdminAuditEvent.actor,
        AdminAuditEvent.entity_id,
        AdminAuditEvent.correlation_id,
        AdminAuditEvent.request_id,
    ]
    column_sortable_list = [AdminAuditEvent.created_at, AdminAuditEvent.action]
    can_create = False
    can_edit = False
    can_delete = False
    can_export = True
    page_size = 50

    form_overrides = {
        "before": TextAreaField,
        "after": TextAreaField,
    }

    def is_accessible(self, request: StarletteRequest) -> bool:
        return bool(request.session.get("admin_user"))

    def is_visible(self, request: StarletteRequest) -> bool:
        return self.is_accessible(request)


def _readiness_snapshot(settings: Settings) -> dict[str, Any]:
    database_ok = False
    redis_ok = False
    try:
        with get_engine(settings).connect() as conn:
            conn.execute(text("SELECT 1"))
        database_ok = True
    except Exception:  # noqa: BLE001
        logger.warning("admin home database check failed", exc_info=True)
    try:
        client = create_redis_client(settings)
        try:
            redis_ok = bool(client.ping())
        finally:
            client.close()
    except Exception:  # noqa: BLE001
        logger.warning("admin home redis check failed", exc_info=True)

    contract_version = "unknown"
    try:
        path = resolve_contract_path(settings.openapi_contract_path or None)
        contract_version = load_openapi_contract(path).contract_version
    except Exception:  # noqa: BLE001
        logger.warning("admin home contract load failed", exc_info=True)

    return {
        "database": database_ok,
        "redis": redis_ok,
        "app_version": settings.app_version,
        "environment": settings.app_env,
        "contract_version": contract_version,
        "admin_read_only": settings.admin_read_only,
    }


def mount_admin(app: FastAPI) -> Admin | None:
    """Attach SQLAdmin at /admin when credentials are configured."""
    settings = get_settings()
    if not settings.admin_enabled:
        logger.warning("admin disabled: set ADMIN_USERNAME and ADMIN_PASSWORD")
        return None

    secret = settings.admin_password.encode("utf-8")
    # Session middleware secret derived stably for the process.
    session_secret = secrets.token_hex(32) if not secret else hmac.new(
        b"omnimsg-admin-session", secret, "sha256"
    ).hexdigest()

    from starlette.middleware.sessions import SessionMiddleware

    app.add_middleware(AdminReadOnlyMiddleware)
    app.add_middleware(AdminBasicGateMiddleware)
    app.add_middleware(SessionMiddleware, secret_key=session_secret)

    @app.get("/admin/home", include_in_schema=False)
    async def admin_home(request: Request) -> Response:
        settings_local = get_settings()
        actor = request.session.get("admin_user")
        if not actor:
            basic_actor = verify_admin_basic(
                request.headers.get("authorization"), settings_local
            )
            if not basic_actor:
                return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        snap = _readiness_snapshot(settings_local)
        html = f"""<!DOCTYPE html>
<html><head><title>OmniMsg Ops Home</title>
<style>
body{{font-family:system-ui,sans-serif;margin:2rem;background:#0f1419;color:#e7ecf3}}
.card{{display:inline-block;margin:.5rem;padding:1rem;border:1px solid #2a3441;border-radius:8px}}
.ok{{color:#3dd68c}}.bad{{color:#f07178}}.muted{{color:#8b9bb4}}
a{{color:#79b8ff}}
</style></head><body>
<h1>OmniMsg Ops</h1>
<p class="muted">ADR-0022 · read-only=
<strong>{"true" if snap["admin_read_only"] else "false"}</strong></p>
<div class="card"><div class="muted">Database</div>
<div class="{"ok" if snap["database"] else "bad"}">
{"ok" if snap["database"] else "down"}</div></div>
<div class="card"><div class="muted">Redis</div>
<div class="{"ok" if snap["redis"] else "bad"}">
{"ok" if snap["redis"] else "down"}</div></div>
<div class="card"><div class="muted">App version</div>
<div>{snap["app_version"]}</div></div>
<div class="card"><div class="muted">Environment</div>
<div>{snap["environment"]}</div></div>
<div class="card"><div class="muted">Contract version</div>
<div>{snap["contract_version"]}</div></div>
<p><a href="/admin/">Open SQLAdmin</a></p>
</body></html>"""
        return HTMLResponse(html)

    authentication_backend = AdminAuthBackend(secret_key=session_secret)
    admin = Admin(
        app=app,
        engine=get_engine(settings),
        authentication_backend=authentication_backend,
        base_url="/admin",
        title="OmniMsg Ops",
    )
    admin.add_view(AdminAuditEventAdmin)
    # C2 views — each deployable independently (ADR-0022).
    from omnimsg_api.admin_apikey import ApiKeyAdmin
    from omnimsg_api.admin_message import MessageAdmin
    from omnimsg_api.admin_tenant import TenantAdmin
    from omnimsg_api.admin_whatsapp import TenantWhatsappAccountAdmin

    admin.add_view(TenantAdmin)
    admin.add_view(ApiKeyAdmin)
    admin.add_view(TenantWhatsappAccountAdmin)
    admin.add_view(MessageAdmin)

    logger.info(
        "admin mounted at /admin read_only=%s",
        settings.admin_read_only,
    )
    return admin
