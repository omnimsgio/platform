"""WhatsApp provisioning retry (P2.4) — deterministic recovery_target dispatch."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from omnimsg_common.db.models import TenantWhatsappAccount
from omnimsg_common.db.session import session_scope
from omnimsg_common.ids import new_id
from omnimsg_common.settings import Settings
from omnimsg_common.whatsapp_lifecycle import (
    EMBEDDED_SIGNUP_STARTED,
    ERROR,
    HEALTH_CHECK_PENDING,
    PHONE_PENDING,
    REASON_RETRY,
    WEBHOOK_PENDING,
    connection_view_from_account,
    transition,
)
from sqlalchemy import select

from omnimsg_api.provisioning import (
    ProvisioningConflictError,
    ProvisioningService,
    ProvisioningStateError,
    ProvisioningUpstreamError,
)
from omnimsg_api.whatsapp_health import HealthService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetryResult:
    status: str
    correlation_id: str
    account_id: str | None
    waba_id: str | None
    phone_number_id: str | None
    status_reason: str | None
    badge: str
    message: str
    checks: dict[str, bool] | None
    last_error: str | None = None
    recovery_target: str | None = None
    updated_at: datetime | None = None
    lifecycle_version: int = 1
    credit_line_attached: bool = False


class RetryService:
    """Restore from ERROR using only ``recovery_target`` (ADR-0020)."""

    def __init__(
        self,
        settings: Settings,
        *,
        provisioning: ProvisioningService | None = None,
        health: HealthService | None = None,
    ) -> None:
        self._settings = settings
        self._provisioning = provisioning or ProvisioningService(settings)
        self._health = health or HealthService(settings)

    def retry(
        self,
        *,
        tenant_id: str,
        correlation_id: str | None = None,
        retry_reason: str = "user",
    ) -> RetryResult:
        correlation_id = (
            correlation_id.strip()
            if correlation_id and correlation_id.strip()
            else new_id("req")
        )
        tenant_id = tenant_id.strip()

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
            if row.status != ERROR:
                raise ProvisioningStateError(
                    f"Retry requires status ERROR, got {row.status}",
                    correlation_id=correlation_id,
                )
            target = (row.recovery_target or "").strip()
            if not target:
                raise ProvisioningStateError(
                    "ERROR has no recovery_target",
                    correlation_id=correlation_id,
                )
            if target == EMBEDDED_SIGNUP_STARTED:
                raise ProvisioningStateError(
                    "Recovery target EMBEDDED_SIGNUP_STARTED requires Embedded Signup",
                    correlation_id=correlation_id,
                )
            if target not in {
                PHONE_PENDING,
                WEBHOOK_PENDING,
                HEALTH_CHECK_PENDING,
            }:
                raise ProvisioningStateError(
                    f"Unsupported recovery_target {target}",
                    correlation_id=correlation_id,
                )

            account_id = row.id
            logger.info(
                "WhatsappProvisioningRetry tenant_id=%s account_id=%s "
                "retry_target=%s retry_reason=%s correlation_id=%s "
                "status_before=ERROR status_reason_before=%s",
                tenant_id,
                account_id,
                target,
                retry_reason,
                correlation_id,
                row.status_reason,
            )

            transition(
                row,
                target,
                status_reason=REASON_RETRY,
                correlation_id=correlation_id,
            )
            row.provisioning_lock_until = None
            session.flush()

        # Dispatch solely by recovery_target (no alternate branching logic).
        if target == PHONE_PENDING:
            return self._connection_result(
                tenant_id, correlation_id=correlation_id, checks=None
            )
        if target == WEBHOOK_PENDING:
            try:
                result = self._provisioning.provision_webhook(
                    tenant_id=tenant_id,
                    correlation_id=correlation_id,
                )
            except (
                ProvisioningConflictError,
                ProvisioningStateError,
                ProvisioningUpstreamError,
            ):
                raise
            return RetryResult(
                status=result.status,
                correlation_id=result.correlation_id,
                account_id=result.account_id,
                waba_id=result.waba_id,
                phone_number_id=result.phone_number_id,
                status_reason=result.status_reason,
                badge=result.badge,
                message=result.message,
                checks=None,
                last_error=result.last_error,
                recovery_target=result.recovery_target,
                updated_at=result.updated_at,
                lifecycle_version=result.lifecycle_version,
                credit_line_attached=result.credit_line_attached,
            )
        # HEALTH_CHECK_PENDING
        health = self._health.check_and_promote(
            tenant_id=tenant_id,
            correlation_id=correlation_id,
        )
        return RetryResult(
            status=health.status,
            correlation_id=health.correlation_id,
            account_id=health.account_id,
            waba_id=health.waba_id,
            phone_number_id=health.phone_number_id,
            status_reason=health.status_reason,
            badge=health.badge,
            message=health.message,
            checks=dict(health.checks),
            last_error=health.last_error,
            recovery_target=health.recovery_target,
            updated_at=health.updated_at,
            lifecycle_version=health.lifecycle_version,
            credit_line_attached=health.credit_line_attached,
        )

    def _connection_result(
        self,
        tenant_id: str,
        *,
        correlation_id: str,
        checks: dict[str, bool] | None,
    ) -> RetryResult:
        with session_scope() as session:
            row = session.scalars(
                select(TenantWhatsappAccount)
                .where(TenantWhatsappAccount.tenant_id == tenant_id)
                .order_by(TenantWhatsappAccount.created_at.desc())
            ).first()
            view = connection_view_from_account(row)
        return RetryResult(
            status=view.status,
            correlation_id=correlation_id,
            account_id=view.account_id,
            waba_id=view.waba_id,
            phone_number_id=view.phone_number_id,
            status_reason=view.status_reason,
            badge=view.badge,
            message=view.message,
            checks=checks,
            last_error=view.last_error,
            recovery_target=view.recovery_target,
            updated_at=view.updated_at,
            lifecycle_version=view.lifecycle_version,
            credit_line_attached=view.credit_line_attached,
        )
