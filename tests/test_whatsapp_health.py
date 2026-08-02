"""Tests for WhatsApp Health Service (P2.3)."""

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
    READY,
)
from sqlalchemy import select
from whatsapp.embedded_signup import MetaGraphError


@pytest.fixture
def health_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_APP_ID", "app_health_123")
    monkeypatch.setenv("META_APP_SECRET", "secret_test")
    get_settings.cache_clear()


def _seed_health_pending(
    tenant_id: str,
    *,
    phone_number_id: str = "pn_health_1",
) -> str:
    account_id = new_id("twa")
    now = datetime.now(UTC)
    with session_scope() as session:
        session.add(
            TenantWhatsappAccount(
                id=account_id,
                tenant_id=tenant_id,
                waba_id="waba_health_1",
                phone_number_id=phone_number_id,
                business_access_token="tok_health",
                credit_line_attached=False,
                status=HEALTH_CHECK_PENDING,
                status_reason="WEBHOOK_SUBSCRIBED",
                phone_registered_at=now,
                webhook_verified_at=now,
                lifecycle_version=1,
            )
        )
    return account_id


def _health(
    client: TestClient,
    seeded_tenant: dict[str, str],
    *,
    correlation_id: str = "req_health_test",
) -> Any:
    return client.post(
        "/v1/whatsapp/health-check",
        headers={
            "X-Tenant-Id": seeded_tenant["tenant_id"],
            "X-Api-Key-Id": seeded_tenant["api_key_id"],
            "X-Correlation-Id": correlation_id,
        },
    )


def test_health_check_all_ok_promotes_ready(
    seeded_tenant: dict[str, str],
    health_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omnimsg_api.main import app

    del health_env
    _seed_health_pending(seeded_tenant["tenant_id"])
    mock = MagicMock()
    mock.health_phone_numbers.return_value = {
        "data": [{"id": "pn_health_1"}],
    }
    mock.get_subscribed_apps.return_value = {
        "data": [{"id": "app_health_123"}],
    }
    monkeypatch.setattr(
        "omnimsg_api.whatsapp_health.MetaEmbeddedSignupClient",
        lambda **_kwargs: mock,
    )

    client = TestClient(app)
    first = _health(client, seeded_tenant)
    assert first.status_code == 200
    body = first.json()
    assert body["status"] == READY
    assert body["status_reason"] == "HEALTH_OK"
    assert body["already_healthy"] is False
    assert body["checks"] == {
        "business_token": True,
        "waba": True,
        "phone_number": True,
        "phone_registered": True,
        "webhook_verified": True,
        "graph_health": True,
    }

    second = _health(client, seeded_tenant, correlation_id="req_health_again")
    assert second.status_code == 200
    assert second.json()["already_healthy"] is True
    assert second.json()["status"] == READY
    assert mock.health_phone_numbers.call_count == 1


def test_health_check_graph_health_fail_keeps_others(
    seeded_tenant: dict[str, str],
    health_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """token/waba/phone/registered/webhook OK but phone not on Graph list."""
    from omnimsg_api.main import app

    del health_env
    _seed_health_pending(
        seeded_tenant["tenant_id"],
        phone_number_id="pn_health_missing",
    )
    mock = MagicMock()
    mock.health_phone_numbers.return_value = {
        "data": [{"id": "pn_other"}],
    }
    mock.get_subscribed_apps.return_value = {
        "data": [{"id": "app_health_123"}],
    }
    monkeypatch.setattr(
        "omnimsg_api.whatsapp_health.MetaEmbeddedSignupClient",
        lambda **_kwargs: mock,
    )

    client = TestClient(app)
    response = _health(client, seeded_tenant)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == ERROR
    assert body["status_reason"] == "HEALTH_CHECK_FAILED"
    assert body["checks"]["business_token"] is True
    assert body["checks"]["waba"] is True
    assert body["checks"]["phone_number"] is True
    assert body["checks"]["phone_registered"] is True
    assert body["checks"]["webhook_verified"] is True
    assert body["checks"]["graph_health"] is False

    with session_scope() as session:
        row = session.scalars(
            select(TenantWhatsappAccount).where(
                TenantWhatsappAccount.phone_number_id == "pn_health_missing"
            )
        ).one()
        assert row.status == ERROR
        assert row.recovery_target == HEALTH_CHECK_PENDING


def test_health_check_token_graph_failure(
    seeded_tenant: dict[str, str],
    health_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omnimsg_api.main import app

    del health_env
    _seed_health_pending(
        seeded_tenant["tenant_id"],
        phone_number_id="pn_health_tok_fail",
    )
    mock = MagicMock()
    mock.health_phone_numbers.side_effect = MetaGraphError(
        "token invalid",
        status_code=401,
        error_code="190",
    )
    monkeypatch.setattr(
        "omnimsg_api.whatsapp_health.MetaEmbeddedSignupClient",
        lambda **_kwargs: mock,
    )

    client = TestClient(app)
    response = _health(client, seeded_tenant)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == ERROR
    assert body["status_reason"] == "HEALTH_CHECK_FAILED"
    assert body["checks"]["business_token"] is False
    assert body["checks"]["graph_health"] is False
