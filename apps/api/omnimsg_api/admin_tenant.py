"""SQLAdmin Tenant view (C2.1) — ADR-0022."""

from __future__ import annotations

from typing import Any

from omnimsg_common.db.models import Tenant
from omnimsg_common.db.session import get_session_factory
from omnimsg_common.ids import new_id
from omnimsg_common.settings import get_settings
from sqladmin import ModelView, action
from starlette.requests import Request
from starlette.responses import RedirectResponse

from omnimsg_api import admin as admin_mod


def _actor(request: Request) -> str:
    user = request.session.get("admin_user")
    return user if isinstance(user, str) and user else "unknown"


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def _audit_meta(request: Request) -> dict[str, str | None]:
    cid = request.headers.get("x-correlation-id") or new_id("req")
    return {
        "correlation_id": cid,
        "request_id": cid,
        "request_ip": _client_ip(request),
        "user_agent": request.headers.get("user-agent"),
    }


def _record_audit(**kwargs: Any) -> None:
    admin_mod.record_admin_audit(**kwargs)


class TenantAdmin(ModelView, model=Tenant):
    name = "Tenant"
    name_plural = "Tenants"
    icon = "fa-solid fa-building"
    column_list = [Tenant.id, Tenant.name, Tenant.status, Tenant.created_at, Tenant.updated_at]
    column_searchable_list = [Tenant.id, Tenant.name, Tenant.status]
    column_sortable_list = [Tenant.created_at, Tenant.name, Tenant.status]
    form_columns = [Tenant.id, Tenant.name, Tenant.status]
    form_include_pk = True
    can_delete = False
    page_size = 50

    def is_accessible(self, request: Request) -> bool:
        return bool(request.session.get("admin_user"))

    def is_visible(self, request: Request) -> bool:
        return self.is_accessible(request)

    async def check_can_create(self, request: Request) -> bool:
        return not get_settings().admin_read_only

    async def check_can_edit(self, request: Request, model: Any) -> bool:
        del model
        return not get_settings().admin_read_only

    async def on_model_change(
        self,
        data: dict[str, Any],
        model: Any,
        is_created: bool,
        request: Request,
    ) -> None:
        if is_created:
            raw = data.get("id")
            raw_id = raw.strip() if isinstance(raw, str) else raw
            if not raw_id:
                data["id"] = new_id("ten")
            status = data.get("status") or "active"
            data["status"] = status
        # Keep status to known values only.
        if data.get("status") not in {"active", "inactive"}:
            data["status"] = "inactive" if data.get("status") else "active"

    async def after_model_change(
        self,
        data: dict[str, Any],
        model: Any,
        is_created: bool,
        request: Request,
    ) -> None:
        meta = _audit_meta(request)
        _record_audit(
            actor=_actor(request),
            action="tenant_create" if is_created else "tenant_update",
            entity_type="Tenant",
            entity_id=getattr(model, "id", None),
            before=None,
            after={
                "id": getattr(model, "id", None),
                "name": getattr(model, "name", None),
                "status": getattr(model, "status", None),
            },
            **meta,
        )

    @action(
        name="deactivate",
        label="Deactivate",
        confirmation_message=(
            "Deactivate selected tenant(s)? Active API keys will stop resolving "
            "until the tenant is set active again."
        ),
    )
    async def deactivate_tenants(self, request: Request) -> RedirectResponse:
        if get_settings().admin_read_only:
            return RedirectResponse(request.url_for("admin:list", identity=self.identity))

        pks = [p for p in request.query_params.get("pks", "").split(",") if p]
        meta = _audit_meta(request)
        factory = get_session_factory()
        with factory() as session:
            for pk in pks:
                row = session.get(Tenant, pk)
                if row is None:
                    continue
                before = {"id": row.id, "status": row.status}
                if row.status == "inactive":
                    continue
                row.status = "inactive"
                session.add(row)
                session.flush()
                _record_audit(
                    actor=_actor(request),
                    action="tenant_deactivate",
                    entity_type="Tenant",
                    entity_id=row.id,
                    before=before,
                    after={"id": row.id, "status": row.status},
                    **meta,
                )
            session.commit()

        return RedirectResponse(request.url_for("admin:list", identity=self.identity))

    @action(
        name="activate",
        label="Activate",
        confirmation_message="Activate selected tenant(s)?",
    )
    async def activate_tenants(self, request: Request) -> RedirectResponse:
        if get_settings().admin_read_only:
            return RedirectResponse(request.url_for("admin:list", identity=self.identity))

        pks = [p for p in request.query_params.get("pks", "").split(",") if p]
        meta = _audit_meta(request)
        factory = get_session_factory()
        with factory() as session:
            for pk in pks:
                row = session.get(Tenant, pk)
                if row is None:
                    continue
                before = {"id": row.id, "status": row.status}
                if row.status == "active":
                    continue
                row.status = "active"
                session.add(row)
                session.flush()
                _record_audit(
                    actor=_actor(request),
                    action="tenant_activate",
                    entity_type="Tenant",
                    entity_id=row.id,
                    before=before,
                    after={"id": row.id, "status": row.status},
                    **meta,
                )
            session.commit()

        return RedirectResponse(request.url_for("admin:list", identity=self.identity))
