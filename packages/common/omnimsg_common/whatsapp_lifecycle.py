"""Tenant WhatsApp connection lifecycle — single source of truth (ADR-0020).

Only Embedded Signup, Provisioning, and Health services may mutate status,
and only via ``transition()`` (or ``bootstrap_ready`` for seed/fixtures).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

# --- Statuses (lifecycle_version = 1) ---

NOT_CONNECTED: Final = "NOT_CONNECTED"
EMBEDDED_SIGNUP_STARTED: Final = "EMBEDDED_SIGNUP_STARTED"
BUSINESS_CONNECTED: Final = "BUSINESS_CONNECTED"
PHONE_PENDING: Final = "PHONE_PENDING"
WEBHOOK_PENDING: Final = "WEBHOOK_PENDING"
HEALTH_CHECK_PENDING: Final = "HEALTH_CHECK_PENDING"
READY: Final = "READY"
ERROR: Final = "ERROR"
DISCONNECTED: Final = "DISCONNECTED"

LIFECYCLE_VERSION: Final = 1

# Statuses that mean ES complete already attached credentials for this tenant.
POST_ATTACH_STATUSES: Final[frozenset[str]] = frozenset(
    {
        PHONE_PENDING,
        WEBHOOK_PENDING,
        HEALTH_CHECK_PENDING,
        READY,
    }
)

# --- status_reason codes ---

REASON_ES_STARTED: Final = "ES_STARTED"
REASON_TOKEN_STORED: Final = "TOKEN_STORED"
REASON_PHONE_PENDING: Final = "PHONE_PENDING"
REASON_PHONE_REGISTERED: Final = "PHONE_REGISTERED"
REASON_ES_EXCHANGE_FAILED: Final = "ES_EXCHANGE_FAILED"
REASON_ES_SUBSCRIBE_FAILED: Final = "ES_SUBSCRIBE_FAILED"
REASON_ES_HEALTH_FAILED: Final = "ES_HEALTH_FAILED"
REASON_PHONE_REGISTRATION_FAILED: Final = "PHONE_REGISTRATION_FAILED"
REASON_WEBHOOK_SUBSCRIBED: Final = "WEBHOOK_SUBSCRIBED"
REASON_WEBHOOK_VERIFY_FAILED: Final = "WEBHOOK_VERIFY_FAILED"
REASON_GRAPH_SUBSCRIBE_FAILED: Final = "GRAPH_SUBSCRIBE_FAILED"
REASON_HEALTH_CHECK_FAILED: Final = "HEALTH_CHECK_FAILED"
REASON_HEALTH_OK: Final = "HEALTH_OK"
REASON_RUNTIME_SEND_FAILED: Final = "RUNTIME_SEND_FAILED"
REASON_APP_REVOKED: Final = "APP_REVOKED"
REASON_WABA_REMOVED: Final = "WABA_REMOVED"
REASON_USER_DISCONNECTED: Final = "USER_DISCONNECTED"
REASON_DEV_BOOTSTRAP: Final = "DEV_BOOTSTRAP"
REASON_RETRY: Final = "RETRY"

ALLOWED_TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    NOT_CONNECTED: frozenset({EMBEDDED_SIGNUP_STARTED}),
    EMBEDDED_SIGNUP_STARTED: frozenset({BUSINESS_CONNECTED, ERROR}),
    BUSINESS_CONNECTED: frozenset({PHONE_PENDING, ERROR}),
    PHONE_PENDING: frozenset({WEBHOOK_PENDING, ERROR}),
    WEBHOOK_PENDING: frozenset({HEALTH_CHECK_PENDING, ERROR}),
    HEALTH_CHECK_PENDING: frozenset({READY, ERROR}),
    READY: frozenset({ERROR, DISCONNECTED}),
    ERROR: frozenset(
        {
            EMBEDDED_SIGNUP_STARTED,
            PHONE_PENDING,
            WEBHOOK_PENDING,
            HEALTH_CHECK_PENDING,
        }
    ),
    DISCONNECTED: frozenset({EMBEDDED_SIGNUP_STARTED}),
}

_MESSAGING_READY: Final[frozenset[str]] = frozenset({READY})

_UI: Final[dict[str, tuple[str, str]]] = {
    NOT_CONNECTED: ("neutral", "WhatsApp nije povezan"),
    EMBEDDED_SIGNUP_STARTED: ("info", "Signup u tijeku"),
    BUSINESS_CONNECTED: ("info", "WABA povezana"),
    PHONE_PENDING: ("warning", "Registriraj broj"),
    WEBHOOK_PENDING: ("warning", "Webhook na čekanju"),
    HEALTH_CHECK_PENDING: ("warning", "Završne provjere"),
    READY: ("success", "Spreman"),
    ERROR: ("error", "Potrebna intervencija"),
    DISCONNECTED: ("neutral", "Odspojeno — poveži ponovo"),
}


class LifecycleTransitionError(ValueError):
    """Illegal lifecycle transition."""


@dataclass(frozen=True)
class ConnectionView:
    """API/UI projection of WhatsApp connection lifecycle."""

    status: str
    status_reason: str | None
    updated_at: datetime | None
    correlation_id: str | None
    last_error: str | None
    recovery_target: str | None
    lifecycle_version: int
    waba_id: str | None
    phone_number_id: str | None
    credit_line_attached: bool
    badge: str
    message: str
    account_id: str | None = None


def messaging_ready_statuses() -> frozenset[str]:
    """Statuses that allow send and inbound processing."""
    return _MESSAGING_READY


def is_messaging_ready(status: str | None) -> bool:
    """Return True only when messaging operations are allowed."""
    return status in _MESSAGING_READY


def ui_for(status: str) -> tuple[str, str]:
    """Return (badge, user_message) for a status."""
    return _UI.get(status, ("neutral", status))


def effective_status(account_status: str | None) -> str:
    """Map missing account to virtual NOT_CONNECTED."""
    if account_status is None:
        return NOT_CONNECTED
    return account_status


def connection_view_from_account(account: object | None) -> ConnectionView:
    """Build ConnectionView from a TenantWhatsappAccount or None."""
    if account is None:
        badge, message = ui_for(NOT_CONNECTED)
        return ConnectionView(
            status=NOT_CONNECTED,
            status_reason=None,
            updated_at=None,
            correlation_id=None,
            last_error=None,
            recovery_target=None,
            lifecycle_version=LIFECYCLE_VERSION,
            waba_id=None,
            phone_number_id=None,
            credit_line_attached=False,
            badge=badge,
            message=message,
            account_id=None,
        )

    status = str(account.status)
    badge, message = ui_for(status)
    if status == ERROR and getattr(account, "last_error", None):
        message = str(account.last_error)
    return ConnectionView(
        status=status,
        status_reason=getattr(account, "status_reason", None),
        updated_at=getattr(account, "updated_at", None),
        correlation_id=getattr(account, "last_correlation_id", None),
        last_error=getattr(account, "last_error", None),
        recovery_target=getattr(account, "recovery_target", None),
        lifecycle_version=int(
            getattr(account, "lifecycle_version", None) or LIFECYCLE_VERSION
        ),
        waba_id=getattr(account, "waba_id", None),
        phone_number_id=getattr(account, "phone_number_id", None),
        credit_line_attached=bool(getattr(account, "credit_line_attached", False)),
        badge=badge,
        message=message,
        account_id=getattr(account, "id", None),
    )


def _apply(
    account: object,
    to_status: str,
    *,
    status_reason: str,
    correlation_id: str,
    last_error: str | None = None,
    recovery_target: str | None = None,
) -> None:
    now = datetime.now(UTC)
    account.status = to_status
    account.status_reason = status_reason
    account.last_correlation_id = correlation_id
    account.updated_at = now
    account.lifecycle_version = (
        getattr(account, "lifecycle_version", None) or LIFECYCLE_VERSION
    )
    if to_status == ERROR:
        detail = last_error or status_reason
        account.last_error = detail[:512] if detail else None
        account.recovery_target = recovery_target
    elif to_status == DISCONNECTED:
        detail = last_error or status_reason
        account.last_error = detail[:512] if detail else None
        account.recovery_target = None
    else:
        account.last_error = None
        account.recovery_target = None


def transition(
    account: object,
    to_status: str,
    *,
    status_reason: str,
    correlation_id: str,
    last_error: str | None = None,
    recovery_target: str | None = None,
    from_status: str | None = None,
) -> None:
    """Apply an allowed lifecycle transition onto ``account`` (mutates in place).

    ``from_status`` defaults to ``account.status``. Use ``NOT_CONNECTED`` when
    creating the first row before status is set.
    """
    current = from_status if from_status is not None else str(account.status)
    allowed = ALLOWED_TRANSITIONS.get(current, frozenset())
    if to_status not in allowed:
        raise LifecycleTransitionError(
            f"Illegal transition {current} → {to_status}"
        )
    if to_status == ERROR and recovery_target is None:
        # Default recovery: restart ES if still early; else stay on current pending.
        if current in {EMBEDDED_SIGNUP_STARTED, BUSINESS_CONNECTED, NOT_CONNECTED}:
            recovery_target = EMBEDDED_SIGNUP_STARTED
        elif current in {
            PHONE_PENDING,
            WEBHOOK_PENDING,
            HEALTH_CHECK_PENDING,
            READY,
        }:
            recovery_target = current if current != READY else HEALTH_CHECK_PENDING
        else:
            recovery_target = EMBEDDED_SIGNUP_STARTED
    if current == ERROR and to_status != ERROR:
        # Full ES restart is always allowed; other recoveries must match target.
        if to_status != EMBEDDED_SIGNUP_STARTED:
            expected = getattr(account, "recovery_target", None)
            if expected and to_status != expected:
                raise LifecycleTransitionError(
                    f"ERROR recovery must go to recovery_target={expected}, got {to_status}"
                )
    _apply(
        account,
        to_status,
        status_reason=status_reason,
        correlation_id=correlation_id,
        last_error=last_error,
        recovery_target=recovery_target,
    )


def bootstrap_ready(
    account: object,
    *,
    correlation_id: str,
    status_reason: str = REASON_DEV_BOOTSTRAP,
) -> None:
    """Seed/fixture helper: force READY without walking the provisioning chain.

    Not for production API/worker paths.
    """
    _apply(
        account,
        READY,
        status_reason=status_reason,
        correlation_id=correlation_id,
        last_error=None,
        recovery_target=None,
    )
