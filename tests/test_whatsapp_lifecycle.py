"""Unit tests for WhatsApp connection lifecycle (ADR-0020)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from omnimsg_common.whatsapp_lifecycle import (
    BUSINESS_CONNECTED,
    DISCONNECTED,
    EMBEDDED_SIGNUP_STARTED,
    ERROR,
    NOT_CONNECTED,
    PHONE_PENDING,
    READY,
    REASON_ES_STARTED,
    REASON_PHONE_PENDING,
    REASON_TOKEN_STORED,
    REASON_USER_DISCONNECTED,
    WEBHOOK_PENDING,
    LifecycleTransitionError,
    bootstrap_ready,
    is_messaging_ready,
    messaging_ready_statuses,
    transition,
)


def _account(status: str = EMBEDDED_SIGNUP_STARTED) -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        status_reason=None,
        last_correlation_id=None,
        updated_at=None,
        lifecycle_version=1,
        last_error=None,
        recovery_target=None,
    )


def test_happy_path_to_ready() -> None:
    account = _account(EMBEDDED_SIGNUP_STARTED)
    transition(
        account,
        BUSINESS_CONNECTED,
        status_reason=REASON_TOKEN_STORED,
        correlation_id="c1",
    )
    transition(
        account,
        PHONE_PENDING,
        status_reason=REASON_PHONE_PENDING,
        correlation_id="c2",
    )
    transition(
        account,
        WEBHOOK_PENDING,
        status_reason="WEBHOOK_SUBSCRIBED",
        correlation_id="c3",
    )
    transition(
        account,
        "HEALTH_CHECK_PENDING",
        status_reason="HEALTH_STARTED",
        correlation_id="c4",
    )
    transition(
        account,
        READY,
        status_reason="HEALTH_OK",
        correlation_id="c5",
    )
    assert account.status == READY
    assert account.last_correlation_id == "c5"
    assert is_messaging_ready(account.status)
    assert account.status in messaging_ready_statuses()


def test_no_downgrade_from_ready() -> None:
    account = _account(READY)
    with pytest.raises(LifecycleTransitionError):
        transition(
            account,
            PHONE_PENDING,
            status_reason=REASON_PHONE_PENDING,
            correlation_id="c",
        )


def test_ready_to_disconnected_then_es() -> None:
    account = _account(READY)
    transition(
        account,
        DISCONNECTED,
        status_reason=REASON_USER_DISCONNECTED,
        correlation_id="c1",
        last_error="revoked",
    )
    assert not is_messaging_ready(account.status)
    transition(
        account,
        EMBEDDED_SIGNUP_STARTED,
        status_reason=REASON_ES_STARTED,
        correlation_id="c2",
    )
    assert account.status == EMBEDDED_SIGNUP_STARTED


def test_error_recovery_target() -> None:
    account = _account(PHONE_PENDING)
    transition(
        account,
        ERROR,
        status_reason="PHONE_REGISTRATION_FAILED",
        correlation_id="c1",
        last_error="pin failed",
        recovery_target=PHONE_PENDING,
    )
    assert account.recovery_target == PHONE_PENDING
    with pytest.raises(LifecycleTransitionError):
        transition(
            account,
            WEBHOOK_PENDING,
            status_reason="RETRY",
            correlation_id="c2",
        )
    transition(
        account,
        PHONE_PENDING,
        status_reason="RETRY",
        correlation_id="c3",
    )
    assert account.status == PHONE_PENDING
    assert account.recovery_target is None


def test_error_allows_es_restart() -> None:
    account = _account(PHONE_PENDING)
    transition(
        account,
        ERROR,
        status_reason="PHONE_REGISTRATION_FAILED",
        correlation_id="c1",
        recovery_target=PHONE_PENDING,
    )
    transition(
        account,
        EMBEDDED_SIGNUP_STARTED,
        status_reason=REASON_ES_STARTED,
        correlation_id="c2",
    )
    assert account.status == EMBEDDED_SIGNUP_STARTED


def test_not_connected_start() -> None:
    account = _account("unused")
    transition(
        account,
        EMBEDDED_SIGNUP_STARTED,
        status_reason=REASON_ES_STARTED,
        correlation_id="c",
        from_status=NOT_CONNECTED,
    )
    assert account.status == EMBEDDED_SIGNUP_STARTED
    assert account.status_reason == REASON_ES_STARTED


def test_bootstrap_ready() -> None:
    account = _account(EMBEDDED_SIGNUP_STARTED)
    bootstrap_ready(account, correlation_id="seed")
    assert account.status == READY
    assert is_messaging_ready(account.status)
