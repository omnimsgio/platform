"""WhatsApp provisioning — phone registration (P2.1) + webhook (P2.2)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from omnimsg_common.db.models import TenantWhatsappAccount
from omnimsg_common.db.session import session_scope
from omnimsg_common.ids import new_id
from omnimsg_common.settings import Settings
from omnimsg_common.whatsapp_lifecycle import (
    ERROR,
    HEALTH_CHECK_PENDING,
    PHONE_PENDING,
    READY,
    REASON_GRAPH_SUBSCRIBE_FAILED,
    REASON_PHONE_REGISTERED,
    REASON_PHONE_REGISTRATION_FAILED,
    REASON_WEBHOOK_SUBSCRIBED,
    REASON_WEBHOOK_VERIFY_FAILED,
    WEBHOOK_PENDING,
    connection_view_from_account,
    transition,
)
from sqlalchemy import select
from whatsapp.embedded_signup import MetaEmbeddedSignupClient, MetaGraphError

logger = logging.getLogger(__name__)

_LOCK_TTL = timedelta(minutes=2)
_POST_REGISTER_STATUSES = frozenset(
    {WEBHOOK_PENDING, HEALTH_CHECK_PENDING, READY}
)
_POST_WEBHOOK_STATUSES = frozenset({HEALTH_CHECK_PENDING, READY})


@dataclass(frozen=True)
class RegisterPhoneResult:
    status: str
    correlation_id: str
    already_registered: bool
    account_id: str | None
    waba_id: str | None
    phone_number_id: str | None
    status_reason: str | None
    badge: str
    message: str
    last_error: str | None = None
    recovery_target: str | None = None
    updated_at: datetime | None = None
    lifecycle_version: int = 1
    credit_line_attached: bool = False


@dataclass(frozen=True)
class ProvisionWebhookResult:
    status: str
    correlation_id: str
    already_provisioned: bool
    account_id: str | None
    waba_id: str | None
    phone_number_id: str | None
    status_reason: str | None
    badge: str
    message: str
    last_error: str | None = None
    recovery_target: str | None = None
    updated_at: datetime | None = None
    lifecycle_version: int = 1
    credit_line_attached: bool = False


class ProvisioningConflictError(Exception):
    """Provisioning lock held."""

    def __init__(self, message: str, *, correlation_id: str) -> None:
        super().__init__(message)
        self.correlation_id = correlation_id


class ProvisioningStateError(Exception):
    """Account not in a valid lifecycle state for this step."""

    def __init__(self, message: str, *, correlation_id: str) -> None:
        super().__init__(message)
        self.correlation_id = correlation_id


class ProvisioningUpstreamError(Exception):
    """Meta/Graph step failed; account may be ERROR."""

    def __init__(self, message: str, *, correlation_id: str) -> None:
        super().__init__(message)
        self.correlation_id = correlation_id


# Back-compat alias for P2.1 imports/tests
ProvisioningRegisterError = ProvisioningUpstreamError


class ProvisioningService:
    """Phone registration and webhook provisioning mutators (ADR-0020)."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: MetaEmbeddedSignupClient | None = None,
    ) -> None:
        self._settings = settings
        self._client = client

    def register_phone(
        self,
        *,
        tenant_id: str,
        pin: str,
        correlation_id: str | None = None,
    ) -> RegisterPhoneResult:
        correlation_id = _cid(correlation_id)
        tenant_id = tenant_id.strip()
        pin = pin.strip()
        if not pin or not pin.isdigit() or len(pin) != 6:
            raise ProvisioningStateError(
                "PIN must be a 6-digit numeric string",
                correlation_id=correlation_id,
            )

        with session_scope() as session:
            row = _latest_account(session, tenant_id)
            if row is None:
                raise ProvisioningStateError(
                    "WhatsApp is not connected for this tenant",
                    correlation_id=correlation_id,
                )

            if row.status in _POST_REGISTER_STATUSES:
                return _register_from_view(
                    connection_view_from_account(row),
                    correlation_id=correlation_id,
                    already_registered=True,
                )

            if row.status != PHONE_PENDING:
                raise ProvisioningStateError(
                    f"Cannot register phone from status {row.status}",
                    correlation_id=correlation_id,
                )

            if not row.phone_number_id or not row.business_access_token:
                raise ProvisioningStateError(
                    "Missing phone_number_id or business access token",
                    correlation_id=correlation_id,
                )

            account_id, phone_number_id, access_token = _acquire_lock(
                row, correlation_id=correlation_id
            )
            session.flush()

        client, owns = self._graph_client()
        try:
            try:
                client.register_phone(
                    phone_number_id=phone_number_id,
                    pin=pin,
                    access_token=access_token,
                    correlation_id=correlation_id,
                )
            except MetaGraphError as exc:
                self._mark_error(
                    account_id,
                    message=str(exc),
                    correlation_id=correlation_id,
                    status_reason=REASON_PHONE_REGISTRATION_FAILED,
                    recovery_target=PHONE_PENDING,
                    error_code=exc.error_code,
                    error_subcode=exc.error_subcode,
                    fbtrace_id=exc.fbtrace_id,
                )
                raise ProvisioningUpstreamError(
                    str(exc),
                    correlation_id=correlation_id,
                ) from exc

            return self._finish_register(account_id, correlation_id=correlation_id)
        finally:
            if owns:
                client.close()

    def provision_webhook(
        self,
        *,
        tenant_id: str,
        correlation_id: str | None = None,
    ) -> ProvisionWebhookResult:
        """Subscribe WABA to app webhooks and confirm via Graph subscribed_apps.

        Hub verify (GET challenge) is app-level on the gateway and is not part of
        this tenant provisioning step.
        """
        correlation_id = _cid(correlation_id)
        tenant_id = tenant_id.strip()
        app_id = (self._settings.meta_app_id or "").strip()
        if not app_id:
            raise ProvisioningStateError(
                "META_APP_ID is required to verify WABA subscribed_apps",
                correlation_id=correlation_id,
            )

        with session_scope() as session:
            row = _latest_account(session, tenant_id)
            if row is None:
                raise ProvisioningStateError(
                    "WhatsApp is not connected for this tenant",
                    correlation_id=correlation_id,
                )

            # Idempotent: already past webhook step, or Graph already confirmed.
            if row.status in _POST_WEBHOOK_STATUSES or row.webhook_verified_at is not None:
                if (
                    row.webhook_verified_at is not None
                    and row.status == WEBHOOK_PENDING
                ):
                    transition(
                        row,
                        HEALTH_CHECK_PENDING,
                        status_reason=REASON_WEBHOOK_SUBSCRIBED,
                        correlation_id=correlation_id,
                    )
                    row.provisioning_lock_until = None
                view = connection_view_from_account(row)
                return _webhook_from_view(
                    view,
                    correlation_id=correlation_id,
                    already_provisioned=True,
                )

            if row.status != WEBHOOK_PENDING:
                raise ProvisioningStateError(
                    f"Cannot provision webhook from status {row.status}",
                    correlation_id=correlation_id,
                )

            if not row.waba_id or not row.business_access_token:
                raise ProvisioningStateError(
                    "Missing waba_id or business access token",
                    correlation_id=correlation_id,
                )

            account_id, _phone, access_token = _acquire_lock(
                row, correlation_id=correlation_id
            )
            waba_id = row.waba_id
            session.flush()

        client, owns = self._graph_client()
        try:
            try:
                client.subscribe_app(
                    waba_id=waba_id,
                    access_token=access_token,
                    correlation_id=correlation_id,
                )
            except MetaGraphError as exc:
                self._mark_error(
                    account_id,
                    message=str(exc),
                    correlation_id=correlation_id,
                    status_reason=REASON_GRAPH_SUBSCRIBE_FAILED,
                    recovery_target=WEBHOOK_PENDING,
                    error_code=exc.error_code,
                    error_subcode=exc.error_subcode,
                    fbtrace_id=exc.fbtrace_id,
                )
                raise ProvisioningUpstreamError(
                    str(exc),
                    correlation_id=correlation_id,
                ) from exc

            try:
                subscribed = client.get_subscribed_apps(
                    waba_id=waba_id,
                    access_token=access_token,
                    correlation_id=correlation_id,
                )
            except MetaGraphError as exc:
                self._mark_error(
                    account_id,
                    message=str(exc),
                    correlation_id=correlation_id,
                    status_reason=REASON_WEBHOOK_VERIFY_FAILED,
                    recovery_target=WEBHOOK_PENDING,
                    error_code=exc.error_code,
                    error_subcode=exc.error_subcode,
                    fbtrace_id=exc.fbtrace_id,
                )
                raise ProvisioningUpstreamError(
                    str(exc),
                    correlation_id=correlation_id,
                ) from exc

            if not _app_subscribed(subscribed, app_id=app_id):
                message = (
                    f"App {app_id} not found in WABA subscribed_apps after subscribe"
                )
                self._mark_error(
                    account_id,
                    message=message,
                    correlation_id=correlation_id,
                    status_reason=REASON_WEBHOOK_VERIFY_FAILED,
                    recovery_target=WEBHOOK_PENDING,
                    error_code=None,
                    error_subcode=None,
                    fbtrace_id=None,
                )
                raise ProvisioningUpstreamError(
                    message,
                    correlation_id=correlation_id,
                )

            return self._finish_webhook(account_id, correlation_id=correlation_id)
        finally:
            if owns:
                client.close()

    def _graph_client(self) -> tuple[MetaEmbeddedSignupClient, bool]:
        if self._client is not None:
            return self._client, False
        return (
            MetaEmbeddedSignupClient(
                app_id=self._settings.meta_app_id or "",
                app_secret=self._settings.meta_app_secret or "",
                api_version=self._settings.meta_graph_api_version,
            ),
            True,
        )

    def _finish_register(
        self,
        account_id: str,
        *,
        correlation_id: str,
    ) -> RegisterPhoneResult:
        now = datetime.now(UTC)
        with session_scope() as session:
            row = session.get(TenantWhatsappAccount, account_id)
            if row is None:
                raise ProvisioningUpstreamError(
                    "WhatsApp account disappeared during register",
                    correlation_id=correlation_id,
                )
            row.phone_registered_at = now
            _clear_provider_errors(row)
            row.provisioning_lock_until = None
            if row.status == PHONE_PENDING:
                transition(
                    row,
                    WEBHOOK_PENDING,
                    status_reason=REASON_PHONE_REGISTERED,
                    correlation_id=correlation_id,
                )
            return _register_from_view(
                connection_view_from_account(row),
                correlation_id=correlation_id,
                already_registered=False,
            )

    def _finish_webhook(
        self,
        account_id: str,
        *,
        correlation_id: str,
    ) -> ProvisionWebhookResult:
        now = datetime.now(UTC)
        with session_scope() as session:
            row = session.get(TenantWhatsappAccount, account_id)
            if row is None:
                raise ProvisioningUpstreamError(
                    "WhatsApp account disappeared during webhook provision",
                    correlation_id=correlation_id,
                )
            # Graph confirmed subscription — only then set local proof.
            row.webhook_verified_at = now
            _clear_provider_errors(row)
            row.provisioning_lock_until = None
            if row.status == WEBHOOK_PENDING:
                transition(
                    row,
                    HEALTH_CHECK_PENDING,
                    status_reason=REASON_WEBHOOK_SUBSCRIBED,
                    correlation_id=correlation_id,
                )
            return _webhook_from_view(
                connection_view_from_account(row),
                correlation_id=correlation_id,
                already_provisioned=False,
            )

    def _mark_error(
        self,
        account_id: str,
        *,
        message: str,
        correlation_id: str,
        status_reason: str,
        recovery_target: str,
        error_code: str | None,
        error_subcode: str | None,
        fbtrace_id: str | None,
    ) -> None:
        with session_scope() as session:
            row = session.get(TenantWhatsappAccount, account_id)
            if row is None:
                return
            row.provider_error_code = error_code
            row.provider_error_subcode = error_subcode
            row.provider_trace_id = fbtrace_id
            row.provisioning_lock_until = None
            if row.status == ERROR:
                row.last_error = message[:512]
                row.status_reason = status_reason
                row.recovery_target = recovery_target
                row.last_correlation_id = correlation_id
                row.updated_at = datetime.now(UTC)
                return
            transition(
                row,
                ERROR,
                status_reason=status_reason,
                correlation_id=correlation_id,
                last_error=message,
                recovery_target=recovery_target,
            )


def _cid(correlation_id: str | None) -> str:
    return (
        correlation_id.strip()
        if correlation_id and correlation_id.strip()
        else new_id("req")
    )


def _latest_account(session: Any, tenant_id: str) -> TenantWhatsappAccount | None:
    return session.scalars(
        select(TenantWhatsappAccount)
        .where(TenantWhatsappAccount.tenant_id == tenant_id)
        .order_by(TenantWhatsappAccount.created_at.desc())
    ).first()


def _acquire_lock(
    row: TenantWhatsappAccount,
    *,
    correlation_id: str,
) -> tuple[str, str | None, str]:
    now = datetime.now(UTC)
    if row.provisioning_lock_until is not None and row.provisioning_lock_until > now:
        raise ProvisioningConflictError(
            "Provisioning is already in progress for this tenant",
            correlation_id=correlation_id,
        )
    row.provisioning_lock_until = now + _LOCK_TTL
    row.provisioning_step_started_at = now
    row.last_correlation_id = correlation_id
    return row.id, row.phone_number_id, row.business_access_token or ""


def _clear_provider_errors(row: TenantWhatsappAccount) -> None:
    row.provider_error_code = None
    row.provider_error_subcode = None
    row.provider_trace_id = None


def _app_subscribed(payload: dict[str, Any], *, app_id: str) -> bool:
    """Return True if Graph subscribed_apps lists our Meta app id."""
    data = payload.get("data")
    if not isinstance(data, list):
        return False
    target = app_id.strip()
    for item in data:
        if not isinstance(item, dict):
            continue
        if str(item.get("id") or "") == target:
            return True
        nested = item.get("whatsapp_business_api_data")
        if isinstance(nested, dict) and str(nested.get("id") or "") == target:
            return True
    return False


def _register_from_view(
    view: object,
    *,
    correlation_id: str,
    already_registered: bool,
) -> RegisterPhoneResult:
    return RegisterPhoneResult(
        status=str(view.status),
        correlation_id=correlation_id,
        already_registered=already_registered,
        account_id=getattr(view, "account_id", None),
        waba_id=getattr(view, "waba_id", None),
        phone_number_id=getattr(view, "phone_number_id", None),
        status_reason=getattr(view, "status_reason", None),
        badge=str(getattr(view, "badge", "")),
        message=str(getattr(view, "message", "")),
        last_error=getattr(view, "last_error", None),
        recovery_target=getattr(view, "recovery_target", None),
        updated_at=getattr(view, "updated_at", None),
        lifecycle_version=int(getattr(view, "lifecycle_version", 1) or 1),
        credit_line_attached=bool(getattr(view, "credit_line_attached", False)),
    )


def _webhook_from_view(
    view: object,
    *,
    correlation_id: str,
    already_provisioned: bool,
) -> ProvisionWebhookResult:
    return ProvisionWebhookResult(
        status=str(view.status),
        correlation_id=correlation_id,
        already_provisioned=already_provisioned,
        account_id=getattr(view, "account_id", None),
        waba_id=getattr(view, "waba_id", None),
        phone_number_id=getattr(view, "phone_number_id", None),
        status_reason=getattr(view, "status_reason", None),
        badge=str(getattr(view, "badge", "")),
        message=str(getattr(view, "message", "")),
        last_error=getattr(view, "last_error", None),
        recovery_target=getattr(view, "recovery_target", None),
        updated_at=getattr(view, "updated_at", None),
        lifecycle_version=int(getattr(view, "lifecycle_version", 1) or 1),
        credit_line_attached=bool(getattr(view, "credit_line_attached", False)),
    )
