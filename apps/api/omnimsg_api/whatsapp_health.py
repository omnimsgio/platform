"""WhatsApp Health Service (P2.3) — Meta-backed health_ok → READY.

Read-only until a single final ``transition()`` to READY or ERROR.
"""

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
    READY,
    REASON_HEALTH_CHECK_FAILED,
    REASON_HEALTH_OK,
    connection_view_from_account,
    transition,
)
from sqlalchemy import select
from whatsapp.embedded_signup import MetaEmbeddedSignupClient, MetaGraphError

from omnimsg_api.provisioning import (
    ProvisioningConflictError,
    ProvisioningStateError,
    _app_subscribed,
)

logger = logging.getLogger(__name__)

_LOCK_TTL = timedelta(minutes=2)

# Public API contract keys (stable for portal).
CHECK_BUSINESS_TOKEN = "business_token"
CHECK_WABA = "waba"
CHECK_PHONE_NUMBER = "phone_number"
CHECK_PHONE_REGISTERED = "phone_registered"
CHECK_WEBHOOK_VERIFIED = "webhook_verified"
CHECK_GRAPH_HEALTH = "graph_health"

CHECK_KEYS: tuple[str, ...] = (
    CHECK_BUSINESS_TOKEN,
    CHECK_WABA,
    CHECK_PHONE_NUMBER,
    CHECK_PHONE_REGISTERED,
    CHECK_WEBHOOK_VERIFIED,
    CHECK_GRAPH_HEALTH,
)


@dataclass(frozen=True)
class HealthCheckResult:
    status: str
    correlation_id: str
    already_healthy: bool
    checks: dict[str, bool]
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


class HealthService:
    """Evaluate ADR-0020 health_ok and promote with one transition."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: MetaEmbeddedSignupClient | None = None,
    ) -> None:
        self._settings = settings
        self._client = client

    def check_and_promote(
        self,
        *,
        tenant_id: str,
        correlation_id: str | None = None,
    ) -> HealthCheckResult:
        correlation_id = (
            correlation_id.strip()
            if correlation_id and correlation_id.strip()
            else new_id("req")
        )
        tenant_id = tenant_id.strip()
        app_id = (self._settings.meta_app_id or "").strip()

        with session_scope() as session:
            row = session.scalars(
                select(TenantWhatsappAccount)
                .where(TenantWhatsappAccount.tenant_id == tenant_id)
                .order_by(TenantWhatsappAccount.created_at.desc())
            ).first()
            if row is None:
                raise ProvisioningStateError(
                    "WhatsApp is not connected for this tenant",
                    correlation_id=correlation_id,
                )

            # Idempotent: already READY — no Graph, no mutation.
            if row.status == READY:
                view = connection_view_from_account(row)
                return _result(
                    view,
                    correlation_id=correlation_id,
                    already_healthy=True,
                    checks={key: True for key in CHECK_KEYS},
                )

            if row.status != HEALTH_CHECK_PENDING:
                raise ProvisioningStateError(
                    f"Cannot run health check from status {row.status}",
                    correlation_id=correlation_id,
                )

            now = datetime.now(UTC)
            if (
                row.provisioning_lock_until is not None
                and row.provisioning_lock_until > now
            ):
                raise ProvisioningConflictError(
                    "Provisioning is already in progress for this tenant",
                    correlation_id=correlation_id,
                )

            row.provisioning_lock_until = now + _LOCK_TTL
            row.provisioning_step_started_at = now
            row.last_correlation_id = correlation_id
            account_id = row.id
            # Snapshot fields for read-only Graph phase (no further status writes yet).
            snapshot = {
                "waba_id": row.waba_id,
                "phone_number_id": row.phone_number_id,
                "access_token": row.business_access_token,
                "phone_registered_at": row.phone_registered_at,
                "webhook_verified_at": row.webhook_verified_at,
            }
            session.flush()

        checks = _empty_checks()
        checks[CHECK_WABA] = bool(snapshot["waba_id"])
        checks[CHECK_PHONE_NUMBER] = bool(snapshot["phone_number_id"])
        checks[CHECK_PHONE_REGISTERED] = snapshot["phone_registered_at"] is not None
        local_webhook = snapshot["webhook_verified_at"] is not None

        graph_error: str | None = None
        owns = self._client is None
        client = self._client or MetaEmbeddedSignupClient(
            app_id=self._settings.meta_app_id or "",
            app_secret=self._settings.meta_app_secret or "",
            api_version=self._settings.meta_graph_api_version,
        )
        try:
            token = (snapshot["access_token"] or "").strip()
            waba_id = (snapshot["waba_id"] or "").strip()
            phone_number_id = (snapshot["phone_number_id"] or "").strip()

            if token and waba_id:
                try:
                    phones_payload = client.health_phone_numbers(
                        waba_id=waba_id,
                        access_token=token,
                        correlation_id=correlation_id,
                    )
                    checks[CHECK_BUSINESS_TOKEN] = True
                    checks[CHECK_GRAPH_HEALTH] = _phone_in_list(
                        phones_payload, phone_number_id=phone_number_id
                    )
                except MetaGraphError as exc:
                    checks[CHECK_BUSINESS_TOKEN] = False
                    checks[CHECK_GRAPH_HEALTH] = False
                    graph_error = str(exc)

            if token and waba_id and app_id and local_webhook:
                try:
                    subscribed = client.get_subscribed_apps(
                        waba_id=waba_id,
                        access_token=token,
                        correlation_id=correlation_id,
                    )
                    checks[CHECK_WEBHOOK_VERIFIED] = _app_subscribed(
                        subscribed, app_id=app_id
                    )
                except MetaGraphError as exc:
                    checks[CHECK_WEBHOOK_VERIFIED] = False
                    if graph_error is None:
                        graph_error = str(exc)
            else:
                checks[CHECK_WEBHOOK_VERIFIED] = False
        finally:
            if owns:
                client.close()

        all_ok = all(checks[key] for key in CHECK_KEYS)
        return self._commit(
            account_id,
            correlation_id=correlation_id,
            checks=checks,
            all_ok=all_ok,
            graph_error=graph_error,
        )

    def _commit(
        self,
        account_id: str,
        *,
        correlation_id: str,
        checks: dict[str, bool],
        all_ok: bool,
        graph_error: str | None,
    ) -> HealthCheckResult:
        with session_scope() as session:
            row = session.get(TenantWhatsappAccount, account_id)
            if row is None:
                raise ProvisioningStateError(
                    "WhatsApp account disappeared during health check",
                    correlation_id=correlation_id,
                )

            row.provisioning_lock_until = None

            # Single lifecycle mutation point.
            if all_ok:
                row.provider_error_code = None
                row.provider_error_subcode = None
                row.provider_trace_id = None
                if row.status == HEALTH_CHECK_PENDING:
                    transition(
                        row,
                        READY,
                        status_reason=REASON_HEALTH_OK,
                        correlation_id=correlation_id,
                    )
            else:
                failed = [key for key in CHECK_KEYS if not checks[key]]
                detail = "Health check failed: " + ", ".join(failed)
                if graph_error:
                    detail = f"{detail}; {graph_error}"
                if row.status == HEALTH_CHECK_PENDING:
                    transition(
                        row,
                        ERROR,
                        status_reason=REASON_HEALTH_CHECK_FAILED,
                        correlation_id=correlation_id,
                        last_error=detail,
                        recovery_target=HEALTH_CHECK_PENDING,
                    )
                elif row.status == ERROR:
                    row.status_reason = REASON_HEALTH_CHECK_FAILED
                    row.recovery_target = HEALTH_CHECK_PENDING
                    row.last_error = detail[:512]
                    row.last_correlation_id = correlation_id
                    row.updated_at = datetime.now(UTC)

            view = connection_view_from_account(row)
            return _result(
                view,
                correlation_id=correlation_id,
                already_healthy=False,
                checks=checks,
            )


def _empty_checks() -> dict[str, bool]:
    return {key: False for key in CHECK_KEYS}


def _phone_in_list(payload: dict[str, Any], *, phone_number_id: str) -> bool:
    if not phone_number_id:
        return False
    data = payload.get("data")
    if not isinstance(data, list):
        return False
    target = phone_number_id.strip()
    for item in data:
        if isinstance(item, dict) and str(item.get("id") or "") == target:
            return True
    return False


def _result(
    view: object,
    *,
    correlation_id: str,
    already_healthy: bool,
    checks: dict[str, bool],
) -> HealthCheckResult:
    return HealthCheckResult(
        status=str(view.status),
        correlation_id=correlation_id,
        already_healthy=already_healthy,
        checks=dict(checks),
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
