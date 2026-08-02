"""SQLAdmin TenantWhatsappAccount view (C2.3) — read-mostly + transition-only."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from omnimsg_common.db.models import TenantWhatsappAccount
from omnimsg_common.db.session import get_session_factory
from omnimsg_common.ids import new_id
from omnimsg_common.settings import get_settings
from omnimsg_common.whatsapp_lifecycle import (
    DISCONNECTED,
    ERROR,
    READY,
    REASON_USER_DISCONNECTED,
    LifecycleTransitionError,
    transition,
)
from sqladmin import ModelView, action
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from omnimsg_api.admin_helpers import actor, audit_meta, public_url, record_audit
from omnimsg_api.provisioning import ProvisioningStateError, ProvisioningUpstreamError
from omnimsg_api.provisioning_retry import RetryService


def _wa_snapshot(row: TenantWhatsappAccount) -> dict[str, Any]:
    """Audit-safe projection — never includes business_access_token."""
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "status": row.status,
        "status_reason": row.status_reason,
        "recovery_target": row.recovery_target,
        "waba_id": row.waba_id,
        "phone_number_id": row.phone_number_id,
        "credit_line_attached": row.credit_line_attached,
        "has_token": bool(row.business_access_token),
        "last_error": row.last_error,
        "lifecycle_version": row.lifecycle_version,
    }


def _mask_token(_obj: Any, _prop: Any) -> str:
    token = getattr(_obj, "business_access_token", None)
    if not token:
        return "—"
    text = str(token)
    if len(text) < 8:
        return "••••"
    return f"••••{text[-4:]}"


class TenantWhatsappAccountAdmin(ModelView, model=TenantWhatsappAccount):
    name = "WhatsApp Account"
    name_plural = "WhatsApp Accounts"
    icon = "fa-brands fa-whatsapp"
    column_list = [
        TenantWhatsappAccount.id,
        TenantWhatsappAccount.tenant_id,
        TenantWhatsappAccount.status,
        TenantWhatsappAccount.status_reason,
        TenantWhatsappAccount.recovery_target,
        TenantWhatsappAccount.waba_id,
        TenantWhatsappAccount.phone_number_id,
        TenantWhatsappAccount.credit_line_attached,
        TenantWhatsappAccount.updated_at,
    ]
    column_details_list = [
        TenantWhatsappAccount.id,
        TenantWhatsappAccount.tenant_id,
        TenantWhatsappAccount.status,
        TenantWhatsappAccount.status_reason,
        TenantWhatsappAccount.recovery_target,
        TenantWhatsappAccount.waba_id,
        TenantWhatsappAccount.phone_number_id,
        TenantWhatsappAccount.business_access_token,
        TenantWhatsappAccount.credit_line_attached,
        TenantWhatsappAccount.last_error,
        TenantWhatsappAccount.last_correlation_id,
        TenantWhatsappAccount.lifecycle_version,
        TenantWhatsappAccount.created_at,
        TenantWhatsappAccount.updated_at,
    ]
    column_formatters = {
        TenantWhatsappAccount.business_access_token: _mask_token,
    }
    column_formatters_detail = {
        TenantWhatsappAccount.business_access_token: _mask_token,
    }
    column_searchable_list = [
        TenantWhatsappAccount.id,
        TenantWhatsappAccount.tenant_id,
        TenantWhatsappAccount.status,
        TenantWhatsappAccount.waba_id,
        TenantWhatsappAccount.phone_number_id,
    ]
    column_sortable_list = [
        TenantWhatsappAccount.updated_at,
        TenantWhatsappAccount.status,
        TenantWhatsappAccount.tenant_id,
    ]
    # No create/edit forms — credentials and status are not operator-editable.
    can_create = False
    can_edit = False
    can_delete = False
    page_size = 50

    def is_accessible(self, request: Request) -> bool:
        return bool(request.session.get("admin_user"))

    def is_visible(self, request: Request) -> bool:
        return self.is_accessible(request)

    def _redirect_list(
        self, request: Request, *, error: str | None = None
    ) -> RedirectResponse:
        url = public_url(request, "admin:list", identity=self.identity)
        if error:
            url = f"{url}?error={quote(error)}"
        return RedirectResponse(url)

    def _take_single_pk(self, request: Request) -> str | None:
        pks = [p for p in request.query_params.get("pks", "").split(",") if p]
        if len(pks) != 1:
            return None
        return pks[0]

    @action(
        name="retry-provisioning",
        label="Retry provisioning",
        confirmation_message=(
            "Retry provisioning for this WhatsApp account? "
            "Only valid when status is ERROR with a recovery_target "
            "(ADR-0020 RetryService → transition)."
        ),
    )
    async def retry_provisioning(self, request: Request) -> Response:
        if get_settings().admin_read_only:
            return self._redirect_list(request)

        pk = self._take_single_pk(request)
        if pk is None:
            return self._redirect_list(
                request, error="Select exactly one WhatsApp account"
            )

        meta = audit_meta(request)
        correlation_id = meta["correlation_id"] or new_id("req")
        factory = get_session_factory()
        try:
            with factory() as session:
                row = session.get(TenantWhatsappAccount, pk)
                if row is None:
                    return self._redirect_list(request, error="Account not found")
                before = _wa_snapshot(row)
                tenant_id = row.tenant_id
            # RetryService opens its own session and calls transition().
            result = RetryService(get_settings()).retry(
                tenant_id=tenant_id,
                correlation_id=correlation_id,
                retry_reason="ops_admin",
            )
            with factory() as session:
                after_row = session.get(TenantWhatsappAccount, pk)
                after = _wa_snapshot(after_row) if after_row else {"status": result.status}
            record_audit(
                actor=actor(request),
                action="whatsapp_retry",
                entity_type="TenantWhatsappAccount",
                entity_id=pk,
                before=before,
                after=after,
                **meta,
            )
        except (ProvisioningStateError, ProvisioningUpstreamError) as exc:
            return self._redirect_list(request, error=str(exc))
        except Exception as exc:  # noqa: BLE001
            return self._redirect_list(request, error=f"Retry failed: {exc}")

        return self._redirect_list(request)

    @action(
        name="mark-disconnected",
        label="Mark disconnected",
        confirmation_message=(
            "Mark this WhatsApp account as DISCONNECTED? "
            "Messaging will stop until Embedded Signup is completed again. "
            "Status change goes only through lifecycle transition()."
        ),
    )
    async def mark_disconnected(self, request: Request) -> Response:
        if get_settings().admin_read_only:
            return self._redirect_list(request)

        pk = self._take_single_pk(request)
        if pk is None:
            return self._redirect_list(
                request, error="Select exactly one WhatsApp account"
            )

        meta = audit_meta(request)
        correlation_id = meta["correlation_id"] or new_id("req")
        factory = get_session_factory()
        try:
            with factory() as session:
                row = session.get(TenantWhatsappAccount, pk)
                if row is None:
                    return self._redirect_list(request, error="Account not found")
                before = _wa_snapshot(row)
                if row.status != READY:
                    return self._redirect_list(
                        request,
                        error=f"Mark disconnected requires READY, got {row.status}",
                    )
                # ADR-0020 / ADR-0022: status only via transition().
                transition(
                    row,
                    DISCONNECTED,
                    status_reason=REASON_USER_DISCONNECTED,
                    correlation_id=correlation_id,
                )
                session.add(row)
                session.commit()
                after = _wa_snapshot(row)
            record_audit(
                actor=actor(request),
                action="whatsapp_mark_disconnected",
                entity_type="TenantWhatsappAccount",
                entity_id=pk,
                before=before,
                after=after,
                **meta,
            )
        except LifecycleTransitionError as exc:
            return self._redirect_list(request, error=str(exc))

        return self._redirect_list(request)


# Imported by CI / architecture tests — do not remove.
_ARCHITECTURE_REQUIRES_TRANSITION = (transition, ERROR, RetryService)
