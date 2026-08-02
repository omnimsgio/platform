"""Tests for WhatsApp webhook provisioning (P2.2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from omnimsg_common.db.models import TenantWhatsappAccount
from omnimsg_common.db.session import session_scope
from omnimsg_common.ids import new_id
from omnimsg_common.settings import get_settings
from omnimsg_common.whatsapp_lifecycle import (
    ERROR,
    HEALTH_CHECK_PENDING,
    WEBHOOK_PENDING,
)
from sqlalchemy import select


@pytest.fixture
def webhook_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_APP_ID", "app_webhook_123")
    monkeypatch.setenv("META_APP_SECRET", "secret_test")
    get_settings.cache_clear()


def _seed_webhook_pending(
    tenant_id: str,
    *,
    phone_number_id: str = "pn_wh_1",
) -> str:
    account_id = new_id("twa")
    with session_scope() as session:
        session.add(
            TenantWhatsappAccount(
                id=account_id,
                tenant_id=tenant_id,
                waba_id="waba_wh_1",
                phone_number_id=phone_number_id,
                business_access_token="tok_wh",
                credit_line_attached=False,
                status=WEBHOOK_PENDING,
                status_reason="PHONE_REGISTERED",
                phone_registered_at=datetime.now(UTC),
                lifecycle_version=1,
            )
        )
    return account_id


def _provision(
    client: TestClient,
    seeded_tenant: dict[str, str],
    *,
    correlation_id: str = "req_wh_test",
) -> Any:
    return client.post(
        "/v1/whatsapp/provision-webhook",
        headers={
            "X-Tenant-Id": seeded_tenant["tenant_id"],
            "X-Api-Key-Id": seeded_tenant["api_key_id"],
            "X-Correlation-Id": correlation_id,
        },
    )


def test_provision_webhook_success_and_idempotent(
    seeded_tenant: dict[str, str],
    webhook_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omnimsg_api.main import app

    del webhook_env
    _seed_webhook_pending(seeded_tenant["tenant_id"])
    mock = MagicMock()
    mock.subscribe_app.return_value = {"success": True}
    mock.get_subscribed_apps.return_value = {
        "data": [{"id": "app_webhook_123"}],
    }
    monkeypatch.setattr(
        "omnimsg_api.provisioning.MetaEmbeddedSignupClient",
        lambda **_kwargs: mock,
    )

    client = TestClient(app)
    first = _provision(client, seeded_tenant)
    assert first.status_code == 200
    body = first.json()
    assert body["status"] == HEALTH_CHECK_PENDING
    assert body["already_provisioned"] is False
    assert body["status_reason"] == "WEBHOOK_SUBSCRIBED"

    with session_scope() as session:
        row = session.scalars(
            select(TenantWhatsappAccount).where(
                TenantWhatsappAccount.tenant_id == seeded_tenant["tenant_id"]
            )
        ).one()
        assert row.status == HEALTH_CHECK_PENDING
        assert row.webhook_verified_at is not None
        assert row.provisioning_lock_until is None

    second = _provision(client, seeded_tenant, correlation_id="req_wh_again")
    assert second.status_code == 200
    assert second.json()["already_provisioned"] is True
    assert second.json()["status"] == HEALTH_CHECK_PENDING
    assert mock.subscribe_app.call_count == 1
    assert mock.get_subscribed_apps.call_count == 1


def test_provision_webhook_subscribe_ok_verify_missing_app(
    seeded_tenant: dict[str, str],
    webhook_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omnimsg_api.main import app

    del webhook_env
    _seed_webhook_pending(
        seeded_tenant["tenant_id"],
        phone_number_id="pn_wh_verify_fail",
    )
    mock = MagicMock()
    mock.subscribe_app.return_value = {"success": True}
    mock.get_subscribed_apps.return_value = {
        "data": [{"id": "some_other_app"}],
    }
    monkeypatch.setattr(
        "omnimsg_api.provisioning.MetaEmbeddedSignupClient",
        lambda **_kwargs: mock,
    )

    client = TestClient(app)
    response = _provision(client, seeded_tenant)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "upstream_failure"

    with session_scope() as session:
        row = session.scalars(
            select(TenantWhatsappAccount).where(
                TenantWhatsappAccount.phone_number_id == "pn_wh_verify_fail"
            )
        ).one()
        assert row.status == ERROR
        assert row.status_reason == "WEBHOOK_VERIFY_FAILED"
        assert row.recovery_target == WEBHOOK_PENDING
        assert row.webhook_verified_at is None


def test_provision_webhook_subscribe_graph_failure(
    seeded_tenant: dict[str, str],
    webhook_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omnimsg_api.main import app
    from whatsapp.embedded_signup import MetaGraphError

    del webhook_env
    _seed_webhook_pending(
        seeded_tenant["tenant_id"],
        phone_number_id="pn_wh_sub_fail",
    )
    mock = MagicMock()
    mock.subscribe_app.side_effect = MetaGraphError(
        "subscribe denied",
        status_code=400,
        error_code="100",
        fbtrace_id="ft_sub",
    )
    monkeypatch.setattr(
        "omnimsg_api.provisioning.MetaEmbeddedSignupClient",
        lambda **_kwargs: mock,
    )

    client = TestClient(app)
    response = _provision(client, seeded_tenant)
    assert response.status_code == 502

    with session_scope() as session:
        row = session.scalars(
            select(TenantWhatsappAccount).where(
                TenantWhatsappAccount.phone_number_id == "pn_wh_sub_fail"
            )
        ).one()
        assert row.status == ERROR
        assert row.status_reason == "GRAPH_SUBSCRIBE_FAILED"
        assert row.provider_trace_id == "ft_sub"
        assert row.webhook_verified_at is None
        assert mock.get_subscribed_apps.call_count == 0


def test_provision_webhook_lock_conflict(
    seeded_tenant: dict[str, str],
    webhook_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omnimsg_api.main import app

    del webhook_env
    account_id = _seed_webhook_pending(
        seeded_tenant["tenant_id"],
        phone_number_id="pn_wh_lock",
    )
    with session_scope() as session:
        row = session.get(TenantWhatsappAccount, account_id)
        assert row is not None
        row.provisioning_lock_until = datetime.now(UTC) + timedelta(minutes=5)

    mock = MagicMock()
    monkeypatch.setattr(
        "omnimsg_api.provisioning.MetaEmbeddedSignupClient",
        lambda **_kwargs: mock,
    )

    client = TestClient(app)
    response = _provision(client, seeded_tenant)
    assert response.status_code == 409
    assert mock.subscribe_app.call_count == 0
