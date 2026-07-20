"""Integration tests: auth, persist, idempotency, WhatsApp channel (Postgres + Redis)."""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from omnimsg_common.db.models import Message, TenantWhatsappAccount
from omnimsg_common.db.session import session_scope
from omnimsg_common.ids import new_id
from omnimsg_common.queue import create_redis_client
from omnimsg_common.settings import get_settings
from omnimsg_worker.main import process_inbound_job, process_job
from sqlalchemy import select
from whatsapp.meta import MetaWhatsAppProvider


def _meta_sign(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


@pytest.fixture
def seeded_whatsapp(seeded_tenant: dict[str, str]) -> dict[str, str]:
    """Attach an active Meta WhatsApp account to the seeded tenant."""
    account_id = new_id("wa")
    phone_number_id = "pn_test_123"
    with session_scope() as session:
        session.add(
            TenantWhatsappAccount(
                id=account_id,
                tenant_id=seeded_tenant["tenant_id"],
                waba_id="waba_test",
                phone_number_id=phone_number_id,
                business_access_token="tok_test_business",
                credit_line_attached=False,
                status="active",
            )
        )
    return {
        **seeded_tenant,
        "whatsapp_account_id": account_id,
        "phone_number_id": phone_number_id,
        "access_token": "tok_test_business",
    }


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
        # WhatsApp without tenant_whatsapp_accounts fails clearly (no stub).
        assert row.status == "failed"

    events = redis_client.lrange(settings.delivery_events_key, 0, -1)
    assert len(events) == 1
    event = json.loads(events[0])
    assert event["event_type"] == "message.delivery_updated.v1"
    assert event["data"]["message_id"] == message_id
    assert event["data"]["status"] == "failed"
    assert event["data"]["provider"] == "meta_whatsapp"
    assert event["data"]["error"]["code"] == "whatsapp_not_configured"


def test_webhook_enqueues_to_inbound_queue(
    seeded_whatsapp: dict[str, str],
    redis_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Signed Meta POST resolves tenant from DB and lands on the inbound Redis queue."""
    monkeypatch.setenv("META_VERIFY_TOKEN", "hub-verify-token")
    monkeypatch.setenv("META_APP_SECRET", "app-secret")
    get_settings.cache_clear()

    settings = get_settings()
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {
                                "phone_number_id": seeded_whatsapp["phone_number_id"],
                            },
                            "statuses": [
                                {
                                    "id": "wamid.inbound_1",
                                    "status": "delivered",
                                    "recipient_id": "385911234567",
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    body = json.dumps(payload, separators=(",", ":")).encode()

    from omnimsg_gateway.main import app as gateway_app

    with TestClient(gateway_app) as client:
        response = client.post(
            "/webhooks/meta/whatsapp",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": _meta_sign("app-secret", body),
                "X-Correlation-Id": "req_inbound_int",
            },
        )

    assert response.status_code == 200
    raw_jobs = redis_client.lrange(settings.inbound_queue_key, 0, -1)
    assert len(raw_jobs) == 1
    job = json.loads(raw_jobs[0])
    assert job["job_type"] == "inbound_webhook"
    assert job["event"]["event_type"] == "webhook.inbound.received.v1"
    assert job["event"]["tenant_id"] == seeded_whatsapp["tenant_id"]
    assert job["event"]["data"]["kind"] == "message_status"
    assert job["event"]["data"]["provider"] == "meta_whatsapp"
    assert job["payload"]["entry"][0]["changes"][0]["value"]["metadata"][
        "phone_number_id"
    ] == seeded_whatsapp["phone_number_id"]


def test_worker_outbound_whatsapp_with_mock_graph(
    seeded_whatsapp: dict[str, str],
    redis_client,
) -> None:
    """Outbound WhatsApp uses tenant account + Meta provider (mocked Graph API)."""
    settings = get_settings()
    message_id = new_id("msg")
    with session_scope() as session:
        session.add(
            Message(
                id=message_id,
                tenant_id=seeded_whatsapp["tenant_id"],
                channel="whatsapp",
                to="+385911234567",
                type="text",
                status="queued",
                idempotency_key=None,
                correlation_id="req_wa_out",
                payload={"type": "text", "text": {"body": "hi graph"}},
            )
        )

    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.read())
        return httpx.Response(
            200,
            json={
                "messaging_product": "whatsapp",
                "messages": [{"id": "wamid.OUTBOUND_1"}],
            },
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))

    def fake_provider(**kwargs: object) -> MetaWhatsAppProvider:
        return MetaWhatsAppProvider(
            phone_number_id=str(kwargs["phone_number_id"]),
            access_token=str(kwargs["access_token"]),
            client=mock_client,
        )

    job = {
        "job_type": "outbound_message",
        "event": {
            "event_type": "message.queued.v1",
            "tenant_id": seeded_whatsapp["tenant_id"],
            "correlation_id": "req_wa_out",
            "data": {
                "message_id": message_id,
                "channel": "whatsapp",
                "to": "+385911234567",
            },
        },
        "payload": {"type": "text", "text": {"body": "hi graph"}},
    }

    with patch("omnimsg_worker.main.MetaWhatsAppProvider", side_effect=fake_provider):
        process_job(job)

    assert captured["url"] == (
        f"https://graph.facebook.com/v21.0/{seeded_whatsapp['phone_number_id']}/messages"
    )
    assert captured["auth"] == f"Bearer {seeded_whatsapp['access_token']}"
    assert captured["body"] == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": "385911234567",
        "type": "text",
        "text": {"body": "hi graph"},
    }

    with session_scope() as session:
        row = session.scalars(select(Message).where(Message.id == message_id)).first()
        assert row is not None
        assert row.status == "accepted"
        assert row.payload["provider_message_id"] == "wamid.OUTBOUND_1"

    events = redis_client.lrange(settings.delivery_events_key, 0, -1)
    assert len(events) == 1
    event = json.loads(events[0])
    assert event["data"]["status"] == "accepted"
    assert event["data"]["provider"] == "meta_whatsapp"


def test_worker_inbound_status_updates_message(
    seeded_whatsapp: dict[str, str],
    redis_client,
) -> None:
    """Inbound message_status webhook updates messages.status and emits delivery event."""
    settings = get_settings()
    message_id = new_id("msg")
    provider_message_id = "wamid.STATUS_DELIVERED"
    with session_scope() as session:
        session.add(
            Message(
                id=message_id,
                tenant_id=seeded_whatsapp["tenant_id"],
                channel="whatsapp",
                to="+385911234567",
                type="text",
                status="accepted",
                idempotency_key=None,
                correlation_id="req_wa_in",
                payload={
                    "type": "text",
                    "text": {"body": "hi"},
                    "provider_message_id": provider_message_id,
                },
            )
        )

    job = {
        "job_type": "inbound_webhook",
        "event": {
            "event_type": "webhook.inbound.received.v1",
            "tenant_id": seeded_whatsapp["tenant_id"],
            "correlation_id": "req_wa_in",
            "data": {
                "provider": "meta_whatsapp",
                "channel": "whatsapp",
                "kind": "message_status",
                "payload_ref": "wh_test",
            },
        },
        "payload": {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "WABA",
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "metadata": {
                                    "phone_number_id": seeded_whatsapp["phone_number_id"],
                                },
                                "statuses": [
                                    {
                                        "id": provider_message_id,
                                        "status": "delivered",
                                        "recipient_id": "385911234567",
                                    }
                                ],
                            },
                        }
                    ],
                }
            ],
        },
    }
    process_inbound_job(job)

    with session_scope() as session:
        row = session.scalars(select(Message).where(Message.id == message_id)).first()
        assert row is not None
        assert row.status == "delivered"

    events = redis_client.lrange(settings.delivery_events_key, 0, -1)
    assert len(events) == 1
    event = json.loads(events[0])
    assert event["event_type"] == "message.delivery_updated.v1"
    assert event["data"]["message_id"] == message_id
    assert event["data"]["status"] == "delivered"
    assert event["data"]["provider"] == "meta_whatsapp"
