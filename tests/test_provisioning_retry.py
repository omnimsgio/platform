"""Tests for WhatsApp provisioning retry (P2.4)."""

from __future__ import annotations

from datetime import UTC, datetime
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
    PHONE_PENDING,
    READY,
    WEBHOOK_PENDING,
)
from sqlalchemy import select
from whatsapp.embedded_signup import MetaGraphError


@pytest.fixture
def retry_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_APP_ID", "app_retry_123")
    monkeypatch.setenv("META_APP_SECRET", "secret_test")
    get_settings.cache_clear()


def _seed_error(
    tenant_id: str,
    *,
    recovery_target: str,
    status_reason: str = "PHONE_REGISTRATION_FAILED",
) -> str:
    account_id = new_id("twa")
    now = datetime.now(UTC)
    with session_scope() as session:
        session.add(
            TenantWhatsappAccount(
                id=account_id,
                tenant_id=tenant_id,
                waba_id="waba_retry_1",
                phone_number_id="pn_retry_1",
                business_access_token="tok_retry",
                credit_line_attached=False,
                status=ERROR,
                status_reason=status_reason,
                last_error="graph failed",
                recovery_target=recovery_target,
                phone_registered_at=(
                    now if recovery_target != PHONE_PENDING else None
                ),
                webhook_verified_at=(
                    now if recovery_target == HEALTH_CHECK_PENDING else None
                ),
                lifecycle_version=1,
            )
        )
    return account_id


def _retry(
    client: TestClient,
    seeded_tenant: dict[str, str],
    *,
    correlation_id: str = "req_retry_test",
) -> Any:
    return client.post(
        "/v1/whatsapp/retry",
        headers={
            "X-Tenant-Id": seeded_tenant["tenant_id"],
            "X-Api-Key-Id": seeded_tenant["api_key_id"],
            "X-Correlation-Id": correlation_id,
        },
    )


def test_retry_phone_pending_restores_without_register(
    seeded_tenant: dict[str, str],
    retry_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omnimsg_api.main import app

    del retry_env
    _seed_error(seeded_tenant["tenant_id"], recovery_target=PHONE_PENDING)
    mock = MagicMock()
    monkeypatch.setattr(
        "omnimsg_api.provisioning.MetaEmbeddedSignupClient",
        lambda **_kwargs: mock,
    )

    client = TestClient(app)
    response = _retry(client, seeded_tenant)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == PHONE_PENDING
    assert body["status_reason"] == "RETRY"
    assert body["checks"] is None
    assert body["badge"]
    assert body["message"]
    assert mock.register_phone.call_count == 0


def test_retry_webhook_pending_dispatches_provision(
    seeded_tenant: dict[str, str],
    retry_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omnimsg_api.main import app

    del retry_env
    _seed_error(
        seeded_tenant["tenant_id"],
        recovery_target=WEBHOOK_PENDING,
        status_reason="GRAPH_SUBSCRIBE_FAILED",
    )
    mock = MagicMock()
    mock.subscribe_app.return_value = {"success": True}
    mock.get_subscribed_apps.return_value = {
        "data": [{"id": "app_retry_123"}],
    }
    monkeypatch.setattr(
        "omnimsg_api.provisioning.MetaEmbeddedSignupClient",
        lambda **_kwargs: mock,
    )

    client = TestClient(app)
    response = _retry(client, seeded_tenant)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == HEALTH_CHECK_PENDING
    assert body["status_reason"] == "WEBHOOK_SUBSCRIBED"
    assert mock.subscribe_app.call_count == 1


def test_retry_health_pending_returns_checks(
    seeded_tenant: dict[str, str],
    retry_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omnimsg_api.main import app

    del retry_env
    _seed_error(
        seeded_tenant["tenant_id"],
        recovery_target=HEALTH_CHECK_PENDING,
        status_reason="HEALTH_CHECK_FAILED",
    )
    mock = MagicMock()
    mock.health_phone_numbers.return_value = {
        "data": [{"id": "pn_retry_1"}],
    }
    mock.get_subscribed_apps.return_value = {
        "data": [{"id": "app_retry_123"}],
    }
    monkeypatch.setattr(
        "omnimsg_api.whatsapp_health.MetaEmbeddedSignupClient",
        lambda **_kwargs: mock,
    )

    client = TestClient(app)
    response = _retry(client, seeded_tenant)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == READY
    assert body["checks"] == {
        "business_token": True,
        "waba": True,
        "phone_number": True,
        "phone_registered": True,
        "webhook_verified": True,
        "graph_health": True,
    }


def test_retry_requires_error(
    seeded_tenant: dict[str, str],
    retry_env: None,
) -> None:
    from omnimsg_api.main import app

    del retry_env
    with session_scope() as session:
        session.add(
            TenantWhatsappAccount(
                id=new_id("twa"),
                tenant_id=seeded_tenant["tenant_id"],
                waba_id="waba_x",
                phone_number_id="pn_x",
                business_access_token="tok",
                credit_line_attached=False,
                status=PHONE_PENDING,
                status_reason="PHONE_PENDING",
                lifecycle_version=1,
            )
        )

    client = TestClient(app)
    response = _retry(client, seeded_tenant)
    assert response.status_code == 409


def test_retry_webhook_graph_failure_returns_error(
    seeded_tenant: dict[str, str],
    retry_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omnimsg_api.main import app

    del retry_env
    _seed_error(
        seeded_tenant["tenant_id"],
        recovery_target=WEBHOOK_PENDING,
        status_reason="GRAPH_SUBSCRIBE_FAILED",
    )
    mock = MagicMock()
    mock.subscribe_app.side_effect = MetaGraphError(
        "subscribe boom",
        status_code=400,
        error_code="100",
    )
    monkeypatch.setattr(
        "omnimsg_api.provisioning.MetaEmbeddedSignupClient",
        lambda **_kwargs: mock,
    )

    client = TestClient(app)
    response = _retry(client, seeded_tenant)
    assert response.status_code == 502
    with session_scope() as session:
        row = session.scalars(
            select(TenantWhatsappAccount).where(
                TenantWhatsappAccount.tenant_id == seeded_tenant["tenant_id"]
            )
        ).first()
        assert row is not None
        assert row.status == ERROR
        assert row.recovery_target == WEBHOOK_PENDING
