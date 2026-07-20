"""Integration tests: auth, persist, idempotency (Postgres + Redis)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from omnimsg_common.db.models import Message
from omnimsg_common.db.session import session_scope
from omnimsg_common.ids import new_id
from omnimsg_common.queue import create_redis_client
from omnimsg_common.settings import get_settings
from omnimsg_worker.main import process_job
from sqlalchemy import select


@pytest.fixture
def redis_client(seeded_tenant: dict[str, str]):
    del seeded_tenant
    settings = get_settings()
    client = create_redis_client(settings)
    try:
        client.ping()
    except Exception as exc:  # noqa: BLE001
        client.close()
        pytest.skip(f"Redis not available: {exc}")
    for key in client.scan_iter(match=f"{settings.redis_key_prefix}*"):
        client.delete(key)
    yield client
    for key in client.scan_iter(match=f"{settings.redis_key_prefix}*"):
        client.delete(key)
    client.close()


def test_auth_resolve_accept_and_reject(seeded_tenant: dict[str, str]) -> None:
    from omnimsg_api.main import app

    client = TestClient(app)
    ok = client.post(
        "/internal/v1/auth/resolve",
        json={"api_key": seeded_tenant["api_key"]},
    )
    assert ok.status_code == 200
    assert ok.json()["tenant_id"] == seeded_tenant["tenant_id"]
    assert ok.json()["api_key_id"] == seeded_tenant["api_key_id"]

    bad = client.post(
        "/internal/v1/auth/resolve",
        json={"api_key": "omni_definitely_invalid_key_xxxxxx"},
    )
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "unauthorized"


def test_create_and_get_message_persists(
    seeded_tenant: dict[str, str],
    redis_client,
) -> None:
    from omnimsg_api.main import app

    del redis_client
    client = TestClient(app)
    create = client.post(
        "/v1/messages",
        json={
            "channel": "whatsapp",
            "to": "+385911234567",
            "type": "text",
            "text": {"body": "Hello from OmniMsg"},
        },
        headers={
            "X-Tenant-Id": seeded_tenant["tenant_id"],
            "X-Correlation-Id": "req_persist_test",
        },
    )
    assert create.status_code == 202
    body = create.json()
    message_id = body["id"]
    assert body["status"] == "queued"

    with session_scope() as session:
        row = session.get(Message, message_id)
        assert row is not None
        assert row.tenant_id == seeded_tenant["tenant_id"]
        assert row.status == "queued"

    got = client.get(
        f"/v1/messages/{message_id}",
        headers={"X-Tenant-Id": seeded_tenant["tenant_id"]},
    )
    assert got.status_code == 200
    assert got.json()["id"] == message_id
    assert got.json()["status"] == "queued"


def test_idempotency_replay_and_conflict(seeded_tenant: dict[str, str]) -> None:
    from omnimsg_api.main import app

    mock_redis = MagicMock()
    with patch("omnimsg_api.main.create_redis_client", return_value=mock_redis):
        client = TestClient(app)
        headers = {
            "X-Tenant-Id": seeded_tenant["tenant_id"],
            "Idempotency-Key": "idem-1",
        }
        payload = {
            "channel": "whatsapp",
            "to": "+385911234567",
            "type": "text",
            "text": {"body": "Hello"},
        }
        first = client.post("/v1/messages", json=payload, headers=headers)
        assert first.status_code == 202
        first_id = first.json()["id"]

        replay = client.post("/v1/messages", json=payload, headers=headers)
        assert replay.status_code == 202
        assert replay.json()["id"] == first_id

        conflict = client.post(
            "/v1/messages",
            json={**payload, "text": {"body": "Different"}},
            headers=headers,
        )
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "conflict"


def test_gateway_bearer_accept_and_rate_limit(
    seeded_tenant: dict[str, str],
    redis_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omnimsg_gateway.main import _check_rate_limit
    from omnimsg_gateway.main import app as gateway_app

    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "2")
    get_settings.cache_clear()

    settings = get_settings()
    assert settings.rate_limit_per_minute == 2
    redis_client.delete(settings.rate_limit_key(seeded_tenant["api_key_id"]))

    assert _check_rate_limit(seeded_tenant["api_key_id"]) is True
    assert _check_rate_limit(seeded_tenant["api_key_id"]) is True
    assert _check_rate_limit(seeded_tenant["api_key_id"]) is False

    resolve_ok = httpx.Response(
        200,
        json={
            "tenant_id": seeded_tenant["tenant_id"],
            "api_key_id": seeded_tenant["api_key_id"],
        },
    )
    upstream_ok = httpx.Response(
        202,
        json={
            "id": "msg_proxy",
            "status": "queued",
            "channel": "whatsapp",
            "created_at": "2026-07-20T12:00:00Z",
            "correlation_id": "req_x",
        },
    )

    with TestClient(gateway_app) as gw:
        http = gw.app.state.http
        http.post = AsyncMock(return_value=resolve_ok)  # type: ignore[method-assign]
        http.request = AsyncMock(return_value=upstream_ok)  # type: ignore[method-assign]
        redis_client.delete(settings.rate_limit_key(seeded_tenant["api_key_id"]))

        response = gw.post(
            "/v1/messages",
            json={
                "channel": "whatsapp",
                "to": "+385911234567",
                "type": "text",
                "text": {"body": "hi"},
            },
            headers={"Authorization": f"Bearer {seeded_tenant['api_key']}"},
        )
        assert response.status_code == 202
        # Trusted headers must be injected; raw Authorization must not be forwarded.
        call_kwargs = http.request.await_args.kwargs
        sent_headers = {k.lower(): v for k, v in call_kwargs["headers"].items()}
        assert sent_headers["x-tenant-id"] == seeded_tenant["tenant_id"]
        assert sent_headers["x-api-key-id"] == seeded_tenant["api_key_id"]
        assert "authorization" not in sent_headers


def test_worker_updates_status_and_emits_event(
    seeded_tenant: dict[str, str],
    redis_client,
) -> None:
    settings = get_settings()
    message_id = new_id("msg")
    with session_scope() as session:
        session.add(
            Message(
                id=message_id,
                tenant_id=seeded_tenant["tenant_id"],
                channel="whatsapp",
                to="+385911234567",
                type="text",
                status="queued",
                idempotency_key=None,
                correlation_id="req_worker",
                payload={"text": {"body": "hi"}, "request": {}},
            )
        )

    job = {
        "job_type": "outbound_message",
        "event": {
            "event_type": "message.queued.v1",
            "tenant_id": seeded_tenant["tenant_id"],
            "correlation_id": "req_worker",
            "data": {
                "message_id": message_id,
                "channel": "whatsapp",
                "to": "+385911234567",
            },
        },
        "payload": {"type": "text", "text": {"body": "hi"}},
    }
    process_job(job)

    with session_scope() as session:
        row = session.scalars(select(Message).where(Message.id == message_id)).first()
        assert row is not None
        assert row.status == "accepted"

    events = redis_client.lrange(settings.delivery_events_key, 0, -1)
    assert len(events) == 1
    event = json.loads(events[0])
    assert event["event_type"] == "message.delivery_updated.v1"
    assert event["data"]["message_id"] == message_id
    assert event["data"]["status"] == "accepted"
