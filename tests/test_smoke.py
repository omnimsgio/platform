"""Smoke tests for foundation app skeletons."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from omnimsg_common.settings import Settings, get_settings

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_openapi_contract_present() -> None:
    path = REPO_ROOT / "packages" / "contracts" / "openapi" / "openapi.yaml"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert text.lstrip().startswith("openapi:")
    assert "/v1/health" in text
    assert "/v1/messages" in text


def test_settings_defaults_use_redis_db_3() -> None:
    settings = Settings(
        database_url="postgresql://omnimsgio:x@postgis:5432/omnimsgio",
        redis_url="redis://infra-redis:6379/3",
        redis_key_prefix="omnimsgio:",
        redis_queue_outbound="queue:outbound",
    )
    assert settings.redis_url.endswith("/3")
    assert settings.outbound_queue_key == "omnimsgio:queue:outbound"


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


def test_api_create_message_enqueues() -> None:
    from omnimsg_api.main import app

    mock_redis = MagicMock()
    with patch("omnimsg_api.main.create_redis_client", return_value=mock_redis):
        client = TestClient(app)
        response = client.post(
            "/v1/messages",
            json={
                "channel": "whatsapp",
                "to": "+385911234567",
                "type": "text",
                "text": {"body": "Hello from OmniMsg"},
            },
            headers={"X-Correlation-Id": "req_test_correlation"},
        )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["channel"] == "whatsapp"
    assert body["correlation_id"] == "req_test_correlation"
    assert body["id"].startswith("msg_")
    mock_redis.lpush.assert_called_once()
    mock_redis.close.assert_called_once()


def test_worker_run_once_processes_job() -> None:
    from omnimsg_worker.main import run_once

    job = {
        "job_type": "outbound_message",
        "event": {
            "event_type": "message.queued.v1",
            "correlation_id": "req_test",
            "data": {"message_id": "msg_test"},
        },
        "payload": {"type": "text", "text": {"body": "hi"}},
    }
    with patch("omnimsg_worker.main.create_redis_client") as create_client:
        with patch("omnimsg_worker.main.dequeue_json", return_value=job) as dequeue:
            assert run_once(timeout_seconds=1) is True
            create_client.assert_called_once()
            dequeue.assert_called_once()
