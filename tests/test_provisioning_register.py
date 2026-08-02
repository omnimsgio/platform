"""Tests for WhatsApp phone registration provisioning (P2.1)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from omnimsg_common.db.models import TenantWhatsappAccount
from omnimsg_common.db.session import session_scope
from omnimsg_common.ids import new_id
from omnimsg_common.whatsapp_lifecycle import (
    ERROR,
    PHONE_PENDING,
    READY,
    WEBHOOK_PENDING,
    bootstrap_ready,
)
from sqlalchemy import select
from whatsapp.embedded_signup import MetaGraphError


def _seed_phone_pending(tenant_id: str, *, phone_number_id: str = "pn_reg_1") -> str:
    account_id = new_id("twa")
    with session_scope() as session:
        session.add(
            TenantWhatsappAccount(
                id=account_id,
                tenant_id=tenant_id,
                waba_id="waba_reg_1",
                phone_number_id=phone_number_id,
                business_access_token="tok_reg",
                credit_line_attached=False,
                status=PHONE_PENDING,
                status_reason="PHONE_PENDING",
                lifecycle_version=1,
            )
        )
    return account_id


def _register(
    client: TestClient,
    seeded_tenant: dict[str, str],
    *,
    pin: str = "123456",
    correlation_id: str = "req_reg_test",
) -> Any:
    return client.post(
        "/v1/whatsapp/register-phone",
        json={"pin": pin},
        headers={
            "X-Tenant-Id": seeded_tenant["tenant_id"],
            "X-Api-Key-Id": seeded_tenant["api_key_id"],
            "X-Correlation-Id": correlation_id,
        },
    )


def test_register_phone_success_and_idempotent(
    seeded_tenant: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omnimsg_api.main import app

    _seed_phone_pending(seeded_tenant["tenant_id"])
    mock = MagicMock()
    mock.register_phone.return_value = {"success": True}
    monkeypatch.setattr(
        "omnimsg_api.provisioning.MetaEmbeddedSignupClient",
        lambda **_kwargs: mock,
    )

    client = TestClient(app)
    first = _register(client, seeded_tenant)
    assert first.status_code == 200
    body = first.json()
    assert body["status"] == WEBHOOK_PENDING
    assert body["already_registered"] is False
    assert body["status_reason"] == "PHONE_REGISTERED"

    with session_scope() as session:
        row = session.scalars(
            select(TenantWhatsappAccount).where(
                TenantWhatsappAccount.tenant_id == seeded_tenant["tenant_id"]
            )
        ).one()
        assert row.status == WEBHOOK_PENDING
        assert row.phone_registered_at is not None
        assert row.provisioning_lock_until is None

    second = _register(client, seeded_tenant, correlation_id="req_reg_again")
    assert second.status_code == 200
    again = second.json()
    assert again["already_registered"] is True
    assert again["status"] == WEBHOOK_PENDING
    assert mock.register_phone.call_count == 1


def test_register_phone_graph_failure(
    seeded_tenant: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omnimsg_api.main import app

    _seed_phone_pending(seeded_tenant["tenant_id"], phone_number_id="pn_reg_fail")
    mock = MagicMock()
    mock.register_phone.side_effect = MetaGraphError(
        "Invalid PIN",
        status_code=400,
        error_code="100",
        error_subcode="33",
        fbtrace_id="trace_1",
    )
    monkeypatch.setattr(
        "omnimsg_api.provisioning.MetaEmbeddedSignupClient",
        lambda **_kwargs: mock,
    )

    client = TestClient(app)
    response = _register(client, seeded_tenant)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "upstream_failure"

    with session_scope() as session:
        row = session.scalars(
            select(TenantWhatsappAccount).where(
                TenantWhatsappAccount.phone_number_id == "pn_reg_fail"
            )
        ).one()
        assert row.status == ERROR
        assert row.status_reason == "PHONE_REGISTRATION_FAILED"
        assert row.recovery_target == PHONE_PENDING
        assert row.provider_error_code == "100"
        assert row.provider_error_subcode == "33"
        assert row.provider_trace_id == "trace_1"
        assert row.provisioning_lock_until is None


def test_register_phone_lock_conflict(
    seeded_tenant: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omnimsg_api.main import app

    account_id = _seed_phone_pending(
        seeded_tenant["tenant_id"],
        phone_number_id="pn_reg_lock",
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
    response = _register(client, seeded_tenant)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"
    assert mock.register_phone.call_count == 0


def test_register_phone_wrong_status(
    seeded_tenant: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omnimsg_api.main import app

    with session_scope() as session:
        account = TenantWhatsappAccount(
            id=new_id("twa"),
            tenant_id=seeded_tenant["tenant_id"],
            waba_id="waba_ready",
            phone_number_id="pn_ready",
            business_access_token="tok",
            credit_line_attached=False,
            status=READY,
            lifecycle_version=1,
        )
        session.add(account)
        bootstrap_ready(account, correlation_id="req_ready")

    mock = MagicMock()
    monkeypatch.setattr(
        "omnimsg_api.provisioning.MetaEmbeddedSignupClient",
        lambda **_kwargs: mock,
    )

    client = TestClient(app)
    response = _register(client, seeded_tenant)
    # READY is post-register → idempotent 200, no Graph
    assert response.status_code == 200
    assert response.json()["already_registered"] is True
    assert mock.register_phone.call_count == 0
