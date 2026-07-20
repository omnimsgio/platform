"""Smoke and contract presence tests (no Postgres required)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from omnimsg_common.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_openapi_contract_present() -> None:
    path = REPO_ROOT / "packages" / "contracts" / "openapi" / "openapi.yaml"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert text.lstrip().startswith("openapi:")
    assert "/v1/health" in text
    assert "/v1/messages" in text
    assert "/v1/messages/{message_id}" in text
    assert "BearerAuth" in text


def test_settings_defaults_use_redis_db_3() -> None:
    settings = Settings(
        database_url="postgresql://omnimsgio:x@postgis:5432/omnimsgio",
        redis_url="redis://infra-redis:6379/3",
        redis_key_prefix="omnimsgio:",
        redis_queue_outbound="queue:outbound",
        redis_queue_inbound="queue:inbound",
        redis_events_delivery="events:delivery",
        meta_verify_token="hub-verify",
        meta_app_secret="app-secret",
    )
    assert settings.redis_url.endswith("/3")
    assert settings.outbound_queue_key == "omnimsgio:queue:outbound"
    assert settings.inbound_queue_key == "omnimsgio:queue:inbound"
    assert settings.delivery_events_key == "omnimsgio:events:delivery"
    assert settings.rate_limit_key("key_1") == "omnimsgio:rl:key_1"
    assert settings.meta_verify_token == "hub-verify"
    assert settings.meta_app_secret == "app-secret"


def test_gateway_health() -> None:
    from omnimsg_gateway.main import app

    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_api_health() -> None:
    from omnimsg_api.main import app

    client = TestClient(app)
    response = client.get("/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_api_rejects_missing_tenant_header() -> None:
    from omnimsg_api.main import app

    client = TestClient(app)
    response = client.post(
        "/v1/messages",
        json={
            "channel": "whatsapp",
            "to": "+385911234567",
            "type": "text",
            "text": {"body": "Hello"},
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_api_validation_error_shape() -> None:
    from omnimsg_api.main import app

    client = TestClient(app)
    response = client.post(
        "/v1/messages",
        json={"channel": "whatsapp", "to": "+385911234567", "type": "text"},
        headers={"X-Tenant-Id": "ten_test"},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert "details" in body["error"]
    assert isinstance(body["error"]["details"], list)


def test_gateway_rejects_missing_bearer() -> None:
    from omnimsg_gateway.main import app

    with TestClient(app) as client:
        response = client.post("/v1/messages", json={})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_stub_provider_accepts_text() -> None:
    from omnimsg_providers.stub import StubMessageProvider

    provider = StubMessageProvider()
    result = provider.send(
        channel="whatsapp",
        to="+385911234567",
        message_type="text",
        payload={"text": {"body": "hi"}},
    )
    assert result.status == "accepted"
    assert result.provider == "stub"


def test_worker_run_once_processes_job() -> None:
    from omnimsg_common.settings import get_settings
    from omnimsg_worker.main import run_once

    settings = get_settings()
    job = {
        "job_type": "outbound_message",
        "event": {
            "event_type": "message.queued.v1",
            "tenant_id": "ten_test",
            "correlation_id": "req_test",
            "data": {
                "message_id": "msg_test",
                "channel": "whatsapp",
                "to": "+385911234567",
            },
        },
        "payload": {"type": "text", "text": {"body": "hi"}},
    }
    with patch("omnimsg_worker.main.create_redis_client") as create_client:
        with patch(
            "omnimsg_worker.main.dequeue_json_any",
            return_value=(settings.outbound_queue_key, job),
        ) as dequeue:
            with patch("omnimsg_worker.main.process_job") as process:
                assert run_once(timeout_seconds=1) is True
                create_client.assert_called_once()
                dequeue.assert_called_once()
                process.assert_called_once_with(job)
