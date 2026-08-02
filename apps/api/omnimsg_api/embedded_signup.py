"""Embedded Signup service — moves WhatsApp connection lifecycle (ADR-0020)."""

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
    BUSINESS_CONNECTED,
    DISCONNECTED,
    EMBEDDED_SIGNUP_STARTED,
    ERROR,
    NOT_CONNECTED,
    PHONE_PENDING,
    POST_ATTACH_STATUSES,
    REASON_ES_EXCHANGE_FAILED,
    REASON_ES_HEALTH_FAILED,
    REASON_ES_STARTED,
    REASON_ES_SUBSCRIBE_FAILED,
    REASON_PHONE_PENDING,
    REASON_TOKEN_STORED,
    connection_view_from_account,
    transition,
)
from sqlalchemy import select
from whatsapp.embedded_signup import MetaEmbeddedSignupClient, MetaGraphError

logger = logging.getLogger(__name__)

TOKEN_SOURCE_ES = "embedded_signup"
_PENDING_TOKEN_PLACEHOLDER = "pending_exchange"


@dataclass(frozen=True)
class StartResult:
    account_id: str
    tenant_id: str
    status: str
    correlation_id: str
    already_started: bool


@dataclass(frozen=True)
class AttachResult:
    account_id: str
    tenant_id: str
    waba_id: str
    phone_number_id: str
    status: str
    correlation_id: str
    already_attached: bool
    meta_business_id: str | None
    status_reason: str | None = None


class EmbeddedSignupConflictError(Exception):
    """Phone number already attached to another tenant."""

    def __init__(self, message: str, *, correlation_id: str) -> None:
        super().__init__(message)
        self.correlation_id = correlation_id


class EmbeddedSignupConfigError(Exception):
    """Missing Meta app credentials for code exchange."""

    def __init__(self, message: str, *, correlation_id: str) -> None:
        super().__init__(message)
        self.correlation_id = correlation_id


class EmbeddedSignupAttachError(Exception):
    """Attach failed after Meta/DB work; account may be status=ERROR."""

    def __init__(
        self,
        message: str,
        *,
        correlation_id: str,
        account_id: str | None = None,
        status: str = ERROR,
    ) -> None:
        super().__init__(message)
        self.correlation_id = correlation_id
        self.account_id = account_id
        self.status = status


class EmbeddedSignupService:
    """Orchestrates WhatsApp phone attach for a tenant via Embedded Signup."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: MetaEmbeddedSignupClient | None = None,
    ) -> None:
        self._settings = settings
        self._client = client

    def start_signup(
        self,
        *,
        tenant_id: str,
        correlation_id: str | None = None,
    ) -> StartResult:
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

            if row is not None and row.status == EMBEDDED_SIGNUP_STARTED:
                return StartResult(
                    account_id=row.id,
                    tenant_id=row.tenant_id,
                    status=row.status,
                    correlation_id=correlation_id,
                    already_started=True,
                )

            if row is not None and row.status in POST_ATTACH_STATUSES:
                return StartResult(
                    account_id=row.id,
                    tenant_id=row.tenant_id,
                    status=row.status,
                    correlation_id=correlation_id,
                    already_started=True,
                )

            if row is None:
                row = TenantWhatsappAccount(
                    id=new_id("twa"),
                    tenant_id=tenant_id,
                    credit_line_attached=False,
                    status=EMBEDDED_SIGNUP_STARTED,
                    lifecycle_version=1,
                )
                session.add(row)
                transition(
                    row,
                    EMBEDDED_SIGNUP_STARTED,
                    status_reason=REASON_ES_STARTED,
                    correlation_id=correlation_id,
                    from_status=NOT_CONNECTED,
                )
            elif row.status in {DISCONNECTED, ERROR}:
                transition(
                    row,
                    EMBEDDED_SIGNUP_STARTED,
                    status_reason=REASON_ES_STARTED,
                    correlation_id=correlation_id,
                    recovery_target=None,
                )
            else:
                # BUSINESS_CONNECTED mid-flight — treat as already started
                return StartResult(
                    account_id=row.id,
                    tenant_id=row.tenant_id,
                    status=row.status,
                    correlation_id=correlation_id,
                    already_started=True,
                )

            session.flush()
            return StartResult(
                account_id=row.id,
                tenant_id=row.tenant_id,
                status=row.status,
                correlation_id=correlation_id,
                already_started=False,
            )

    def get_connection(self, *, tenant_id: str):
        with session_scope() as session:
            row = session.scalars(
                select(TenantWhatsappAccount)
                .where(TenantWhatsappAccount.tenant_id == tenant_id)
                .order_by(TenantWhatsappAccount.created_at.desc())
            ).first()
            if row is not None:
                session.expunge(row)
            return connection_view_from_account(row)

    def attach_tenant_phone(
        self,
        *,
        tenant_id: str,
        api_key_id: str | None,
        code: str,
        waba_id: str,
        phone_number_id: str,
        meta_business_id: str | None = None,
        correlation_id: str | None = None,
    ) -> AttachResult:
        correlation_id = (
            correlation_id.strip()
            if correlation_id and correlation_id.strip()
            else new_id("req")
        )
        tenant_id = tenant_id.strip()
        waba_id = waba_id.strip()
        phone_number_id = phone_number_id.strip()
        code = code.strip()
        meta_business_id = (
            meta_business_id.strip() if meta_business_id and meta_business_id.strip() else None
        )

        logger.info(
            "es attach start tenant_id=%s phone_number_id=%s waba_id=%s "
            "correlation_id=%s api_key_id=%s",
            tenant_id,
            phone_number_id,
            waba_id,
            correlation_id,
            api_key_id,
        )

        existing = self._find_by_phone(phone_number_id)
        if existing is not None:
            if existing.tenant_id != tenant_id:
                raise EmbeddedSignupConflictError(
                    "WhatsApp phone number is already attached to another tenant",
                    correlation_id=correlation_id,
                )
            if existing.status in POST_ATTACH_STATUSES:
                logger.info(
                    "es attach idempotent tenant_id=%s phone_number_id=%s "
                    "correlation_id=%s status=%s",
                    tenant_id,
                    phone_number_id,
                    correlation_id,
                    existing.status,
                )
                return AttachResult(
                    account_id=existing.id,
                    tenant_id=existing.tenant_id,
                    waba_id=existing.waba_id or waba_id,
                    phone_number_id=existing.phone_number_id or phone_number_id,
                    status=existing.status,
                    correlation_id=correlation_id,
                    already_attached=True,
                    meta_business_id=existing.meta_business_id,
                    status_reason=existing.status_reason,
                )

        if not self._settings.meta_app_id or not self._settings.meta_app_secret:
            raise EmbeddedSignupConfigError(
                "META_APP_ID and META_APP_SECRET are required for Embedded Signup",
                correlation_id=correlation_id,
            )

        account = self._ensure_started_row(
            existing=existing,
            tenant_id=tenant_id,
            waba_id=waba_id,
            phone_number_id=phone_number_id,
            meta_business_id=meta_business_id,
            correlation_id=correlation_id,
        )
        account_id = account.id

        owns_client = self._client is None
        client = self._client or MetaEmbeddedSignupClient(
            app_id=self._settings.meta_app_id,
            app_secret=self._settings.meta_app_secret,
            api_version=self._settings.meta_graph_api_version,
        )
        try:
            try:
                token_payload = client.exchange_code(code, correlation_id=correlation_id)
            except MetaGraphError as exc:
                self._mark_error(
                    account_id,
                    str(exc),
                    correlation_id,
                    status_reason=REASON_ES_EXCHANGE_FAILED,
                    recovery_target=EMBEDDED_SIGNUP_STARTED,
                )
                self._capture_sentry(exc, correlation_id=correlation_id, tenant_id=tenant_id)
                raise EmbeddedSignupAttachError(
                    str(exc),
                    correlation_id=correlation_id,
                    account_id=account_id,
                ) from exc

            access_token = str(token_payload.get("access_token") or "").strip()
            if not access_token:
                message = "Meta code exchange returned no access_token"
                self._mark_error(
                    account_id,
                    message,
                    correlation_id,
                    status_reason=REASON_ES_EXCHANGE_FAILED,
                    recovery_target=EMBEDDED_SIGNUP_STARTED,
                )
                raise EmbeddedSignupAttachError(
                    message,
                    correlation_id=correlation_id,
                    account_id=account_id,
                )

            token_expires_at = _expires_at_from_payload(token_payload)
            self._store_business_connected(
                account_id,
                access_token=access_token,
                token_expires_at=token_expires_at,
                waba_id=waba_id,
                phone_number_id=phone_number_id,
                meta_business_id=meta_business_id,
                correlation_id=correlation_id,
            )

            try:
                client.subscribe_app(
                    waba_id=waba_id,
                    access_token=access_token,
                    correlation_id=correlation_id,
                )
            except MetaGraphError as exc:
                self._mark_error(
                    account_id,
                    str(exc),
                    correlation_id,
                    status_reason=REASON_ES_SUBSCRIBE_FAILED,
                    recovery_target=PHONE_PENDING,
                )
                self._capture_sentry(exc, correlation_id=correlation_id, tenant_id=tenant_id)
                raise EmbeddedSignupAttachError(
                    str(exc),
                    correlation_id=correlation_id,
                    account_id=account_id,
                ) from exc

            try:
                health = client.health_phone_numbers(
                    waba_id=waba_id,
                    access_token=access_token,
                    correlation_id=correlation_id,
                )
                phones = health.get("data") if isinstance(health, dict) else None
                if not isinstance(phones, list):
                    raise EmbeddedSignupAttachError(
                        "Token health check failed: unexpected phone_numbers response",
                        correlation_id=correlation_id,
                        account_id=account_id,
                    )
            except MetaGraphError as exc:
                self._mark_error(
                    account_id,
                    str(exc),
                    correlation_id,
                    status_reason=REASON_ES_HEALTH_FAILED,
                    recovery_target=PHONE_PENDING,
                )
                self._capture_sentry(exc, correlation_id=correlation_id, tenant_id=tenant_id)
                raise EmbeddedSignupAttachError(
                    str(exc),
                    correlation_id=correlation_id,
                    account_id=account_id,
                ) from exc
            except EmbeddedSignupAttachError as exc:
                self._mark_error(
                    account_id,
                    str(exc),
                    correlation_id,
                    status_reason=REASON_ES_HEALTH_FAILED,
                    recovery_target=PHONE_PENDING,
                )
                raise

            self._audit_attached(
                tenant_id=tenant_id,
                api_key_id=api_key_id,
                waba_id=waba_id,
                phone_number_id=phone_number_id,
                meta_business_id=meta_business_id,
                correlation_id=correlation_id,
                account_id=account_id,
            )
            logger.info(
                "es attach success tenant_id=%s phone_number_id=%s "
                "correlation_id=%s account_id=%s status=%s",
                tenant_id,
                phone_number_id,
                correlation_id,
                account_id,
                PHONE_PENDING,
            )
            return AttachResult(
                account_id=account_id,
                tenant_id=tenant_id,
                waba_id=waba_id,
                phone_number_id=phone_number_id,
                status=PHONE_PENDING,
                correlation_id=correlation_id,
                already_attached=False,
                meta_business_id=meta_business_id,
                status_reason=REASON_PHONE_PENDING,
            )
        finally:
            if owns_client:
                client.close()

    def _find_by_phone(self, phone_number_id: str) -> TenantWhatsappAccount | None:
        with session_scope() as session:
            row = session.scalars(
                select(TenantWhatsappAccount).where(
                    TenantWhatsappAccount.phone_number_id == phone_number_id
                )
            ).first()
            if row is None:
                return None
            session.expunge(row)
            return row

    def _ensure_started_row(
        self,
        *,
        existing: TenantWhatsappAccount | None,
        tenant_id: str,
        waba_id: str,
        phone_number_id: str,
        meta_business_id: str | None,
        correlation_id: str,
    ) -> TenantWhatsappAccount:
        with session_scope() as session:
            if existing is not None:
                row = session.get(TenantWhatsappAccount, existing.id)
                if row is None:
                    raise EmbeddedSignupAttachError(
                        "WhatsApp account disappeared during attach",
                        correlation_id=correlation_id,
                    )
            else:
                row = session.scalars(
                    select(TenantWhatsappAccount)
                    .where(TenantWhatsappAccount.tenant_id == tenant_id)
                    .order_by(TenantWhatsappAccount.created_at.desc())
                ).first()
                if row is None:
                    row = TenantWhatsappAccount(
                        id=new_id("twa"),
                        tenant_id=tenant_id,
                        credit_line_attached=False,
                        status=EMBEDDED_SIGNUP_STARTED,
                        lifecycle_version=1,
                    )
                    session.add(row)
                    transition(
                        row,
                        EMBEDDED_SIGNUP_STARTED,
                        status_reason=REASON_ES_STARTED,
                        correlation_id=correlation_id,
                        from_status=NOT_CONNECTED,
                    )
                elif row.status in {DISCONNECTED, ERROR}:
                    transition(
                        row,
                        EMBEDDED_SIGNUP_STARTED,
                        status_reason=REASON_ES_STARTED,
                        correlation_id=correlation_id,
                    )
                elif row.status != EMBEDDED_SIGNUP_STARTED:
                    # Keep row; credentials refresh path
                    pass

            row.tenant_id = tenant_id
            row.waba_id = waba_id
            row.phone_number_id = phone_number_id
            if (
                not row.business_access_token
                or row.business_access_token == _PENDING_TOKEN_PLACEHOLDER
            ):
                row.business_access_token = _PENDING_TOKEN_PLACEHOLDER
            row.graph_api_version = self._settings.meta_graph_api_version
            row.token_source = TOKEN_SOURCE_ES
            row.meta_business_id = meta_business_id
            if row.status != EMBEDDED_SIGNUP_STARTED:
                # Re-enter signup from mid states only via explicit transitions above
                pass
            row.last_correlation_id = correlation_id
            session.flush()
            session.expunge(row)
            return row

    def _store_business_connected(
        self,
        account_id: str,
        *,
        access_token: str,
        token_expires_at: datetime | None,
        waba_id: str,
        phone_number_id: str,
        meta_business_id: str | None,
        correlation_id: str,
    ) -> None:
        now = datetime.now(UTC)
        with session_scope() as session:
            row = session.get(TenantWhatsappAccount, account_id)
            if row is None:
                return
            row.business_access_token = access_token
            row.token_created_at = now
            row.token_expires_at = token_expires_at
            row.graph_api_version = self._settings.meta_graph_api_version
            row.token_source = TOKEN_SOURCE_ES
            row.waba_id = waba_id
            row.phone_number_id = phone_number_id
            if meta_business_id is not None:
                row.meta_business_id = meta_business_id

            if row.status == EMBEDDED_SIGNUP_STARTED:
                transition(
                    row,
                    BUSINESS_CONNECTED,
                    status_reason=REASON_TOKEN_STORED,
                    correlation_id=correlation_id,
                )
            if row.status == BUSINESS_CONNECTED:
                transition(
                    row,
                    PHONE_PENDING,
                    status_reason=REASON_PHONE_PENDING,
                    correlation_id=correlation_id,
                )
            elif row.status == ERROR:
                # recovery_target should be EMBEDDED_SIGNUP_STARTED — restart path
                transition(
                    row,
                    EMBEDDED_SIGNUP_STARTED,
                    status_reason=REASON_ES_STARTED,
                    correlation_id=correlation_id,
                )
                transition(
                    row,
                    BUSINESS_CONNECTED,
                    status_reason=REASON_TOKEN_STORED,
                    correlation_id=correlation_id,
                )
                transition(
                    row,
                    PHONE_PENDING,
                    status_reason=REASON_PHONE_PENDING,
                    correlation_id=correlation_id,
                )

    def _mark_error(
        self,
        account_id: str,
        message: str,
        correlation_id: str,
        *,
        status_reason: str,
        recovery_target: str,
    ) -> None:
        with session_scope() as session:
            row = session.get(TenantWhatsappAccount, account_id)
            if row is None:
                return
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

    def _audit_attached(
        self,
        *,
        tenant_id: str,
        api_key_id: str | None,
        waba_id: str,
        phone_number_id: str,
        meta_business_id: str | None,
        correlation_id: str,
        account_id: str,
    ) -> None:
        logger.info(
            "WhatsappAccountAttached tenant_id=%s api_key_id=%s account_id=%s "
            "waba_id=%s phone_number_id=%s meta_business_id=%s "
            "correlation_id=%s status=%s",
            tenant_id,
            api_key_id,
            account_id,
            waba_id,
            phone_number_id,
            meta_business_id,
            correlation_id,
            PHONE_PENDING,
        )

    def _capture_sentry(
        self,
        exc: BaseException,
        *,
        correlation_id: str,
        tenant_id: str,
    ) -> None:
        dsn = (self._settings.sentry_dsn or "").strip()
        if not dsn:
            return
        try:
            import sentry_sdk

            with sentry_sdk.push_scope() as scope:
                scope.set_tag("correlation_id", correlation_id)
                scope.set_tag("tenant_id", tenant_id)
                sentry_sdk.capture_exception(exc)
        except Exception:
            logger.exception(
                "sentry capture failed correlation_id=%s",
                correlation_id,
            )


def _expires_at_from_payload(token_payload: dict[str, Any]) -> datetime | None:
    expires_in = token_payload.get("expires_in")
    if isinstance(expires_in, int) and expires_in > 0:
        return datetime.now(UTC) + timedelta(seconds=expires_in)
    if isinstance(expires_in, float) and expires_in > 0:
        return datetime.now(UTC) + timedelta(seconds=int(expires_in))
    return None
