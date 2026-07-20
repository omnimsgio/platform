"""Unit tests for Meta WhatsApp webhook verify + HMAC + enqueue."""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from omnimsg_common.settings import Settings, get_settings
from omnimsg_gateway.meta_webhook import (
    classify_webhook_kind,
    extract_external_event_id,
    extract_phone_number_id,
    verify_meta_signature,
)


def _sign(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_verify_meta_signature_accepts_valid() -> None:
    body = b'{"object":"whatsapp_business_account"}'
    assert verify_meta_signature(
        app_secret="app-secret",
        body=body,
        signature_header=_sign("app-secret", body),
    )


def test_verify_meta_signature_rejects_bad() -> None:
    body = b'{"object":"whatsapp_business_account"}'
    assert not verify_meta_signature(
        app_secret="app-secret",
        body=body,
        signature_header=_sign("other-secret", body),
    )
    assert not verify_meta_signature(
        app_secret="app-secret",
        body=body,
        signature_header=None,
    )
    assert not verify_meta_signature(
        app_secret="",
        body=body,
        signature_header=_sign("app-secret", body),
    )


def test_extract_phone_and_kind() -> None:
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
                                "display_phone_number": "16505551111",
                                "phone_number_id": "pn_123",
                            },
                            "statuses": [
                                {
                                    "id": "wamid.STATUS",
                                    "status": "delivered",
                                    "recipient_id": "385911111111",
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    assert extract_phone_number_id(payload) == "pn_123"
    assert classify_webhook_kind(payload) == "message_status"
    assert extract_external_event_id(payload) == "wamid.STATUS"


def test_hub_challenge_accept_and_reject() -> None:
    get_settings.cache_clear()
    with patch(
        "omnimsg_gateway.main.get_settings",
        return_value=Settings(
            meta_verify_token="hub-verify-token",
            meta_app_secret="app-secret",
        ),
    ):
        from omnimsg_gateway.main import app

        with TestClient(app) as client:
            ok = client.get(
                "/webhooks/meta/whatsapp",
                params={
                    "hub.mode": "subscribe",
                    "hub.verify_token": "hub-verify-token",
                    "hub.challenge": "challenge-123",
                },
            )
            assert ok.status_code == 200
            assert ok.text == "challenge-123"

            bad = client.get(
                "/webhooks/meta/whatsapp",
                params={
                    "hub.mode": "subscribe",
                    "hub.verify_token": "wrong",
                    "hub.challenge": "challenge-123",
                },
            )
            assert bad.status_code == 403
    get_settings.cache_clear()


def test_post_rejects_bad_signature() -> None:
    get_settings.cache_clear()
    with patch(
        "omnimsg_gateway.main.get_settings",
        return_value=Settings(
            meta_verify_token="hub-verify-token",
            meta_app_secret="app-secret",
        ),
    ):
        from omnimsg_gateway.main import app

        body = b'{"object":"whatsapp_business_account","entry":[]}'
        with TestClient(app) as client:
            response = client.post(
                "/webhooks/meta/whatsapp",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": _sign("wrong", body),
                },
            )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"
    get_settings.cache_clear()


def test_post_enqueues_inbound_event() -> None:
    get_settings.cache_clear()
    settings = Settings(
        meta_verify_token="hub-verify-token",
        meta_app_secret="app-secret",
        redis_key_prefix="omnimsgio:",
        redis_queue_inbound="queue:inbound",
    )
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": "pn_123"},
                            "statuses": [{"id": "wamid.1", "status": "sent"}],
                        },
                    }
                ],
            }
        ],
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    mock_redis = MagicMock()

    with (
        patch("omnimsg_gateway.main.get_settings", return_value=settings),
        patch("omnimsg_gateway.main._resolve_whatsapp_tenant", return_value="ten_test"),
        patch("omnimsg_gateway.main.create_redis_client", return_value=mock_redis),
    ):
        from omnimsg_gateway.main import app

        with TestClient(app) as client:
            response = client.post(
                "/webhooks/meta/whatsapp",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": _sign("app-secret", body),
                    "X-Correlation-Id": "req_webhook_test",
                },
            )

    assert response.status_code == 200
    mock_redis.setex.assert_called_once()
    mock_redis.lpush.assert_called_once()
    queue_key, raw_job = mock_redis.lpush.call_args.args
    assert queue_key == "omnimsgio:queue:inbound"
    job = json.loads(raw_job)
    assert job["job_type"] == "inbound_webhook"
    assert job["event"]["event_type"] == "webhook.inbound.received.v1"
    assert job["event"]["tenant_id"] == "ten_test"
    assert job["event"]["correlation_id"] == "req_webhook_test"
    assert job["event"]["data"]["provider"] == "meta_whatsapp"
    assert job["event"]["data"]["kind"] == "message_status"
    assert job["event"]["data"]["payload_ref"]
    assert job["event"]["data"]["external_event_id"] == "wamid.1"
    mock_redis.close.assert_called_once()
    get_settings.cache_clear()
