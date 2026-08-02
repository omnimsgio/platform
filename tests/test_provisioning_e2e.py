"""P2.5 E2E / CI golden path for WhatsApp provisioning lifecycle."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from omnimsg_common.db.models import TenantWhatsappAccount
from omnimsg_common.db.session import session_scope
from omnimsg_common.settings import get_settings
from omnimsg_common.whatsapp_lifecycle import (
    ERROR,
    HEALTH_CHECK_PENDING,
    NOT_CONNECTED,
    PHONE_PENDING,
    READY,
    WEBHOOK_PENDING,
)
from sqlalchemy import select
from whatsapp.embedded_signup import MetaGraphError


@pytest.fixture
def e2e_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_APP_ID", "app_e2e_123")
    monkeypatch.setenv("META_APP_SECRET", "secret_e2e")
    monkeypatch.setenv("META_ES_CONFIG_ID", "es_cfg_e2e")
    get_settings.cache_clear()


def _headers(seeded_tenant: dict[str, str], *, correlation_id: str) -> dict[str, str]:
    return {
        "X-Tenant-Id": seeded_tenant["tenant_id"],
        "X-Api-Key-Id": seeded_tenant["api_key_id"],
        "X-Correlation-Id": correlation_id,
    }


def _connection(client: TestClient, seeded_tenant: dict[str, str]) -> Any:
    return client.get(
        "/v1/whatsapp/connection",
        headers=_headers(seeded_tenant, correlation_id="req_conn"),
    )


def _install_meta_mocks(
    monkeypatch: pytest.MonkeyPatch,
    *,
    phone_number_id: str = "pn_e2e_1",
    register_side_effect: Exception | None = None,
) -> MagicMock:
    """Single client mock shared across ES / provisioning / health modules."""
    mock = MagicMock()
    mock.exchange_code.return_value = {
        "access_token": "tok_e2e",
        "token_type": "bearer",
    }
    mock.debug_token.return_value = {
        "data": {"is_valid": True, "app_id": "app_e2e_123"},
    }
    mock.subscribe_app.return_value = {"success": True}
    mock.get_subscribed_apps.return_value = {
        "data": [{"id": "app_e2e_123"}],
    }
    if register_side_effect is not None:
        mock.register_phone.side_effect = register_side_effect
    else:
        mock.register_phone.return_value = {"success": True}
    mock.health_phone_numbers.return_value = {
        "data": [{"id": phone_number_id}],
    }

    factory = lambda **_kwargs: mock  # noqa: E731
    monkeypatch.setattr(
        "omnimsg_api.embedded_signup.MetaEmbeddedSignupClient",
        factory,
    )
    monkeypatch.setattr(
        "omnimsg_api.provisioning.MetaEmbeddedSignupClient",
        factory,
    )
    monkeypatch.setattr(
        "omnimsg_api.whatsapp_health.MetaEmbeddedSignupClient",
        factory,
    )
    return mock


def test_golden_path_not_connected_to_ready_retry_ready(
    seeded_tenant: dict[str, str],
    e2e_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CI golden path: NOT_CONNECTED → READY → re-health READY; plus fail→retry→READY."""
    from omnimsg_api.main import app

    del e2e_env
    phone_number_id = "pn_e2e_1"
    mock = _install_meta_mocks(monkeypatch, phone_number_id=phone_number_id)
    client = TestClient(app)

    conn0 = _connection(client, seeded_tenant)
    assert conn0.status_code == 200
    assert conn0.json()["status"] == NOT_CONNECTED

    start = client.post(
        "/v1/whatsapp/embedded-signup/start",
        headers=_headers(seeded_tenant, correlation_id="req_es_start"),
    )
    assert start.status_code == 200

    complete = client.post(
        "/v1/whatsapp/embedded-signup/complete",
        headers=_headers(seeded_tenant, correlation_id="req_es_done"),
        json={
            "code": "es_code_e2e",
            "waba_id": "waba_e2e_1",
            "phone_number_id": phone_number_id,
        },
    )
    assert complete.status_code == 200
    assert complete.json()["status"] == PHONE_PENDING

    register = client.post(
        "/v1/whatsapp/register-phone",
        headers=_headers(seeded_tenant, correlation_id="req_reg"),
        json={"pin": "123456"},
    )
    assert register.status_code == 200
    assert register.json()["status"] == WEBHOOK_PENDING

    webhook = client.post(
        "/v1/whatsapp/provision-webhook",
        headers=_headers(seeded_tenant, correlation_id="req_wh"),
    )
    assert webhook.status_code == 200
    assert webhook.json()["status"] == HEALTH_CHECK_PENDING

    health = client.post(
        "/v1/whatsapp/health-check",
        headers=_headers(seeded_tenant, correlation_id="req_health"),
    )
    assert health.status_code == 200
    assert health.json()["status"] == READY
    assert health.json()["already_healthy"] is False
    graph_calls_after_ready = mock.health_phone_numbers.call_count

    # Idempotent health: READY → health again → READY, no re-provision Graph.
    health2 = client.post(
        "/v1/whatsapp/health-check",
        headers=_headers(seeded_tenant, correlation_id="req_health_idem"),
    )
    assert health2.status_code == 200
    body2 = health2.json()
    assert body2["status"] == READY
    assert body2["already_healthy"] is True
    assert body2["status_reason"] == "HEALTH_OK"
    assert mock.health_phone_numbers.call_count == graph_calls_after_ready
    assert mock.subscribe_app.call_count >= 1

    # Force ERROR + PHONE_PENDING recovery, then walk back to READY (retry path).
    with session_scope() as session:
        row = session.scalars(
            select(TenantWhatsappAccount).where(
                TenantWhatsappAccount.tenant_id == seeded_tenant["tenant_id"]
            )
        ).one()
        from omnimsg_common.whatsapp_lifecycle import (
            REASON_PHONE_REGISTRATION_FAILED,
            transition,
        )

        transition(
            row,
            ERROR,
            status_reason=REASON_PHONE_REGISTRATION_FAILED,
            correlation_id="req_force_err",
            last_error="forced for golden path",
            recovery_target=PHONE_PENDING,
        )
        row.phone_registered_at = None
        row.webhook_verified_at = None

    retry = client.post(
        "/v1/whatsapp/retry",
        headers=_headers(seeded_tenant, correlation_id="req_retry"),
    )
    assert retry.status_code == 200
    assert retry.json()["status"] == PHONE_PENDING
    assert retry.json()["status_reason"] == "RETRY"

    register2 = client.post(
        "/v1/whatsapp/register-phone",
        headers=_headers(seeded_tenant, correlation_id="req_reg2"),
        json={"pin": "654321"},
    )
    assert register2.status_code == 200
    assert register2.json()["status"] == WEBHOOK_PENDING

    webhook2 = client.post(
        "/v1/whatsapp/provision-webhook",
        headers=_headers(seeded_tenant, correlation_id="req_wh2"),
    )
    assert webhook2.status_code == 200

    health3 = client.post(
        "/v1/whatsapp/health-check",
        headers=_headers(seeded_tenant, correlation_id="req_health3"),
    )
    assert health3.status_code == 200
    assert health3.json()["status"] == READY

    final = _connection(client, seeded_tenant)
    assert final.json()["status"] == READY


def test_e2e_register_fail_then_retry(
    seeded_tenant: dict[str, str],
    e2e_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omnimsg_api.main import app

    del e2e_env
    phone_number_id = "pn_e2e_fail"
    mock = _install_meta_mocks(
        monkeypatch,
        phone_number_id=phone_number_id,
        register_side_effect=MetaGraphError(
            "pin invalid",
            status_code=400,
            error_code="133005",
        ),
    )
    client = TestClient(app)

    assert (
        client.post(
            "/v1/whatsapp/embedded-signup/start",
            headers=_headers(seeded_tenant, correlation_id="req_es_s"),
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/v1/whatsapp/embedded-signup/complete",
            headers=_headers(seeded_tenant, correlation_id="req_es_c"),
            json={
                "code": "es_code_fail",
                "waba_id": "waba_e2e_fail",
                "phone_number_id": phone_number_id,
            },
        ).json()["status"]
        == PHONE_PENDING
    )

    fail = client.post(
        "/v1/whatsapp/register-phone",
        headers=_headers(seeded_tenant, correlation_id="req_reg_fail"),
        json={"pin": "111111"},
    )
    assert fail.status_code == 502

    with session_scope() as session:
        row = session.scalars(
            select(TenantWhatsappAccount).where(
                TenantWhatsappAccount.tenant_id == seeded_tenant["tenant_id"]
            )
        ).one()
        assert row.status == ERROR
        assert row.recovery_target == PHONE_PENDING

    retry = client.post(
        "/v1/whatsapp/retry",
        headers=_headers(seeded_tenant, correlation_id="req_retry_fail"),
    )
    assert retry.status_code == 200
    assert retry.json()["status"] == PHONE_PENDING

    mock.register_phone.side_effect = None
    mock.register_phone.return_value = {"success": True}

    ok = client.post(
        "/v1/whatsapp/register-phone",
        headers=_headers(seeded_tenant, correlation_id="req_reg_ok"),
        json={"pin": "222222"},
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == WEBHOOK_PENDING
