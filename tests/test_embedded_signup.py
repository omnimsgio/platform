"""Tests for WhatsApp Embedded Signup + connection lifecycle."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from omnimsg_common.db.models import Tenant, TenantWhatsappAccount
from omnimsg_common.db.session import session_scope
from omnimsg_common.ids import new_id
from omnimsg_common.settings import get_settings
from omnimsg_common.whatsapp_lifecycle import (
    ERROR,
    PHONE_PENDING,
    READY,
    bootstrap_ready,
)
from sqlalchemy import select
from whatsapp.embedded_signup import MetaEmbeddedSignupClient, MetaGraphError


@pytest.fixture
def es_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_APP_ID", "app_test_123")
    monkeypatch.setenv("META_APP_SECRET", "secret_test")
    get_settings.cache_clear()


def _mock_client(
    *,
    exchange: dict[str, Any] | Exception | None = None,
    subscribe: dict[str, Any] | Exception | None = None,
    health: dict[str, Any] | Exception | None = None,
    share: dict[str, Any] | Exception | None = None,
) -> MagicMock:
    client = MagicMock()
    if isinstance(exchange, Exception):
        client.exchange_code.side_effect = exchange
    else:
        client.exchange_code.return_value = exchange or {
            "access_token": "tok_es_business",
            "expires_in": 3600,
        }
    if isinstance(subscribe, Exception):
        client.subscribe_app.side_effect = subscribe
    else:
        client.subscribe_app.return_value = subscribe or {"success": True}
    if isinstance(health, Exception):
        client.health_phone_numbers.side_effect = health
    else:
        client.health_phone_numbers.return_value = health or {
            "data": [{"id": "pn_es_1"}],
        }
    if isinstance(share, Exception):
        client.share_credit_line.side_effect = share
    else:
        client.share_credit_line.return_value = share or {
            "allocation_config_id": "alloc_1",
            "waba_id": "waba_es_1",
        }
    return client


def _enable_credit_line(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_EXTENDED_CREDIT_LINE_ID", "credit_line_1")
    monkeypatch.setenv("META_BUSINESS_ACCESS_TOKEN", "sys_tok")
    monkeypatch.setenv("META_CREDIT_LINE_CURRENCY", "EUR")
    get_settings.cache_clear()


def _complete(
    client: TestClient,
    seeded_tenant: dict[str, str],
    *,
    phone_number_id: str = "pn_es_1",
    correlation_id: str = "req_es_test",
) -> Any:
    return client.post(
        "/v1/whatsapp/embedded-signup/complete",
        json={
            "code": "AQ_test_code",
            "waba_id": "waba_es_1",
            "phone_number_id": phone_number_id,
            "meta_business_id": "bm_es_1",
        },
        headers={
            "X-Tenant-Id": seeded_tenant["tenant_id"],
            "X-Api-Key-Id": seeded_tenant["api_key_id"],
            "X-Correlation-Id": correlation_id,
        },
    )


def test_es_start_and_connection_status(
    seeded_tenant: dict[str, str],
    es_env: None,
) -> None:
    from omnimsg_api.main import app

    del es_env
    client = TestClient(app)
    headers = {
        "X-Tenant-Id": seeded_tenant["tenant_id"],
        "X-Api-Key-Id": seeded_tenant["api_key_id"],
        "X-Correlation-Id": "req_es_start",
    }
    before = client.get("/v1/whatsapp/connection", headers=headers)
    assert before.status_code == 200
    assert before.json()["status"] == "NOT_CONNECTED"

    started = client.post("/v1/whatsapp/embedded-signup/start", headers=headers)
    assert started.status_code == 200
    body = started.json()
    assert body["status"] == "EMBEDDED_SIGNUP_STARTED"
    assert body["already_started"] is False

    after = client.get("/v1/whatsapp/connection", headers=headers)
    assert after.status_code == 200
    conn = after.json()
    assert conn["status"] == "EMBEDDED_SIGNUP_STARTED"
    assert conn["status_reason"] == "ES_STARTED"
    assert conn["updated_at"]
    assert conn["correlation_id"] == "req_es_start"
    assert conn["badge"]
    assert conn["message"]


def test_es_complete_success_and_idempotent(
    seeded_tenant: dict[str, str],
    es_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omnimsg_api.main import app

    del es_env
    mock = _mock_client()
    monkeypatch.setattr(
        "omnimsg_api.embedded_signup.MetaEmbeddedSignupClient",
        lambda **_kwargs: mock,
    )

    client = TestClient(app)
    first = _complete(client, seeded_tenant)
    assert first.status_code == 200
    body = first.json()
    assert body["status"] == PHONE_PENDING
    assert body["already_attached"] is False
    assert body["correlation_id"] == "req_es_test"
    assert body["phone_number_id"] == "pn_es_1"
    assert body["tenant_id"] == seeded_tenant["tenant_id"]

    with session_scope() as session:
        row = session.scalars(
            select(TenantWhatsappAccount).where(
                TenantWhatsappAccount.phone_number_id == "pn_es_1"
            )
        ).one()
        assert row.status == PHONE_PENDING
        assert row.business_access_token == "tok_es_business"
        assert row.token_source == "embedded_signup"
        assert row.last_correlation_id == "req_es_test"
        assert row.meta_business_id == "bm_es_1"
        assert row.status_reason == "PHONE_PENDING"
        assert row.lifecycle_version == 1

    second = _complete(client, seeded_tenant, correlation_id="req_es_retry")
    assert second.status_code == 200
    again = second.json()
    assert again["already_attached"] is True
    assert again["account_id"] == body["account_id"]
    assert again["correlation_id"] == "req_es_retry"
    assert again["status"] == PHONE_PENDING
    assert mock.exchange_code.call_count == 1


def test_es_complete_health_failure_leaves_error(
    seeded_tenant: dict[str, str],
    es_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omnimsg_api.main import app

    del es_env
    mock = _mock_client(
        health=MetaGraphError("health failed", status_code=400, error_code="100"),
    )
    monkeypatch.setattr(
        "omnimsg_api.embedded_signup.MetaEmbeddedSignupClient",
        lambda **_kwargs: mock,
    )

    client = TestClient(app)
    response = _complete(client, seeded_tenant, phone_number_id="pn_es_fail")
    assert response.status_code == 502
    err = response.json()["error"]
    assert err["correlation_id"] == "req_es_test"
    assert err["code"] == "upstream_failure"

    with session_scope() as session:
        row = session.scalars(
            select(TenantWhatsappAccount).where(
                TenantWhatsappAccount.phone_number_id == "pn_es_fail"
            )
        ).one()
        assert row.status == ERROR
        assert row.status_reason == "ES_HEALTH_FAILED"
        assert row.recovery_target == PHONE_PENDING
        assert row.last_error
        assert "health" in row.last_error.lower() or "failed" in row.last_error.lower()


def test_es_complete_conflict_other_tenant(
    seeded_tenant: dict[str, str],
    es_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omnimsg_api.main import app

    del es_env
    other_id = "ten_other"
    with session_scope() as session:
        session.add(Tenant(id=other_id, name="Other", status="active"))
        account = TenantWhatsappAccount(
            id=new_id("twa"),
            tenant_id=other_id,
            waba_id="waba_other",
            phone_number_id="pn_taken",
            business_access_token="tok_other",
            credit_line_attached=False,
            status=READY,
            lifecycle_version=1,
        )
        session.add(account)
        bootstrap_ready(account, correlation_id="req_other")

    mock = _mock_client()
    monkeypatch.setattr(
        "omnimsg_api.embedded_signup.MetaEmbeddedSignupClient",
        lambda **_kwargs: mock,
    )

    client = TestClient(app)
    response = _complete(client, seeded_tenant, phone_number_id="pn_taken")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"
    assert response.json()["error"]["correlation_id"] == "req_es_test"
    assert mock.exchange_code.call_count == 0


def test_es_complete_requires_tenant_header(es_env: None) -> None:
    from omnimsg_api.main import app

    del es_env
    client = TestClient(app)
    response = client.post(
        "/v1/whatsapp/embedded-signup/complete",
        json={
            "code": "AQ_test",
            "waba_id": "waba_1",
            "phone_number_id": "pn_1",
        },
        headers={"X-Correlation-Id": "req_no_tenant"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["correlation_id"] == "req_no_tenant"


def test_es_complete_missing_meta_config(
    seeded_tenant: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omnimsg_api.main import app

    monkeypatch.setenv("META_APP_ID", "")
    monkeypatch.setenv("META_APP_SECRET", "")
    get_settings.cache_clear()

    client = TestClient(app)
    response = _complete(client, seeded_tenant)
    assert response.status_code == 503
    assert response.json()["error"]["correlation_id"] == "req_es_test"


def test_share_credit_line_posts_query_and_bearer() -> None:
    http = MagicMock()
    response = MagicMock()
    response.is_success = True
    response.json.return_value = {
        "allocation_config_id": "alloc_1",
        "waba_id": "waba_1",
    }
    http.post.return_value = response
    graph = MetaEmbeddedSignupClient(
        app_id="app",
        app_secret="secret",
        api_version="v21.0",
        base_url="https://graph.facebook.com",
        client=http,
    )
    body = graph.share_credit_line(
        credit_line_id="credit_line_1",
        waba_id="waba_1",
        currency="EUR",
        system_token="sys_tok",
        correlation_id="req_credit",
    )
    assert body["allocation_config_id"] == "alloc_1"
    http.post.assert_called_once()
    args, kwargs = http.post.call_args
    assert args[0] == (
        "https://graph.facebook.com/v21.0/"
        "credit_line_1/whatsapp_credit_sharing_and_attach"
    )
    assert kwargs["params"] == {"waba_id": "waba_1", "waba_currency": "EUR"}
    assert kwargs["headers"]["Authorization"] == "Bearer sys_tok"


def test_es_complete_credit_line_unconfigured(
    seeded_tenant: dict[str, str],
    es_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omnimsg_api.main import app

    del es_env
    mock = _mock_client()
    monkeypatch.setattr(
        "omnimsg_api.embedded_signup.MetaEmbeddedSignupClient",
        lambda **_kwargs: mock,
    )

    client = TestClient(app)
    response = _complete(client, seeded_tenant, phone_number_id="pn_es_nocredit")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == PHONE_PENDING
    assert body["credit_line_attached"] is False
    assert mock.share_credit_line.call_count == 0

    with session_scope() as session:
        row = session.scalars(
            select(TenantWhatsappAccount).where(
                TenantWhatsappAccount.phone_number_id == "pn_es_nocredit"
            )
        ).one()
        assert row.credit_line_attached is False
        assert row.credit_allocation_config_id is None


def test_es_complete_credit_line_success(
    seeded_tenant: dict[str, str],
    es_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omnimsg_api.main import app

    del es_env
    _enable_credit_line(monkeypatch)
    mock = _mock_client(share={"allocation_config_id": "alloc_99", "waba_id": "waba_es_1"})
    monkeypatch.setattr(
        "omnimsg_api.embedded_signup.MetaEmbeddedSignupClient",
        lambda **_kwargs: mock,
    )

    client = TestClient(app)
    response = _complete(client, seeded_tenant, phone_number_id="pn_es_credit")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == PHONE_PENDING
    assert body["credit_line_attached"] is True
    mock.share_credit_line.assert_called_once_with(
        credit_line_id="credit_line_1",
        waba_id="waba_es_1",
        currency="EUR",
        system_token="sys_tok",
        correlation_id="req_es_test",
    )

    with session_scope() as session:
        row = session.scalars(
            select(TenantWhatsappAccount).where(
                TenantWhatsappAccount.phone_number_id == "pn_es_credit"
            )
        ).one()
        assert row.status == PHONE_PENDING
        assert row.credit_line_attached is True
        assert row.credit_allocation_config_id == "alloc_99"


def test_es_complete_credit_line_failure_does_not_block(
    seeded_tenant: dict[str, str],
    es_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omnimsg_api.main import app

    del es_env
    _enable_credit_line(monkeypatch)
    mock = _mock_client(
        share=MetaGraphError("credit share failed", status_code=400, error_code="100"),
    )
    monkeypatch.setattr(
        "omnimsg_api.embedded_signup.MetaEmbeddedSignupClient",
        lambda **_kwargs: mock,
    )

    client = TestClient(app)
    response = _complete(client, seeded_tenant, phone_number_id="pn_es_credit_fail")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == PHONE_PENDING
    assert body["credit_line_attached"] is False
    assert mock.share_credit_line.call_count == 1

    with session_scope() as session:
        row = session.scalars(
            select(TenantWhatsappAccount).where(
                TenantWhatsappAccount.phone_number_id == "pn_es_credit_fail"
            )
        ).one()
        assert row.status == PHONE_PENDING
        assert row.credit_line_attached is False
        assert row.credit_allocation_config_id is None


def test_es_complete_credit_line_idempotent(
    seeded_tenant: dict[str, str],
    es_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omnimsg_api.main import app

    del es_env
    _enable_credit_line(monkeypatch)
    mock = _mock_client()
    monkeypatch.setattr(
        "omnimsg_api.embedded_signup.MetaEmbeddedSignupClient",
        lambda **_kwargs: mock,
    )

    client = TestClient(app)
    first = _complete(client, seeded_tenant, phone_number_id="pn_es_credit_again")
    assert first.status_code == 200
    assert first.json()["credit_line_attached"] is True

    second = _complete(
        client,
        seeded_tenant,
        phone_number_id="pn_es_credit_again",
        correlation_id="req_es_credit_retry",
    )
    assert second.status_code == 200
    again = second.json()
    assert again["already_attached"] is True
    assert again["status"] == PHONE_PENDING
    assert again["credit_line_attached"] is True
    assert mock.share_credit_line.call_count == 1
