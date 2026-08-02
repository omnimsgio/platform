"""Unit tests for Meta WhatsApp Cloud API adapter (Graph request shape)."""

from __future__ import annotations

import json

import httpx
import pytest
from whatsapp.meta import MetaWhatsAppProvider


def test_graph_text_request_shape() -> None:
    """POST body and URL match Cloud API v21.0 messages endpoint."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == "https://graph.facebook.com/v21.0/pn_123/messages"
        assert request.headers["Authorization"] == "Bearer tok_abc"
        assert request.headers["Content-Type"] == "application/json"
        payload = json.loads(request.read())
        assert payload == {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": "385911234567",
            "type": "text",
            "text": {"body": "Hello OmniMsg"},
        }
        return httpx.Response(
            200,
            json={
                "messaging_product": "whatsapp",
                "contacts": [{"input": "385911234567", "wa_id": "385911234567"}],
                "messages": [{"id": "wamid.HBgLMTIz"}],
            },
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    with MetaWhatsAppProvider(
        phone_number_id="pn_123",
        access_token="tok_abc",
        client=client,
    ) as provider:
        result = provider.send(
            channel="whatsapp",
            to="+385911234567",
            message_type="text",
            payload={"text": {"body": "Hello OmniMsg"}},
        )

    assert result.status == "accepted"
    assert result.provider == "meta_whatsapp"
    assert result.provider_message_id == "wamid.HBgLMTIz"
    assert result.error_code is None


def test_graph_maps_error_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            400,
            json={
                "error": {
                    "message": "(#131030) Recipient phone number not in allowed list",
                    "type": "OAuthException",
                    "code": 131030,
                }
            },
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    with MetaWhatsAppProvider(
        phone_number_id="pn_123",
        access_token="tok_abc",
        client=client,
    ) as provider:
        result = provider.send(
            channel="whatsapp",
            to="385911234567",
            message_type="text",
            payload={"text": {"body": "hi"}},
        )

    assert result.status == "failed"
    assert result.provider == "meta_whatsapp"
    assert result.error_code == "131030"
    assert "allowed list" in (result.error_message or "")
    assert result.provider_message_id is None


def test_rejects_unsupported_type_without_http() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    with MetaWhatsAppProvider(
        phone_number_id="pn_123",
        access_token="tok_abc",
        client=client,
    ) as provider:
        result = provider.send(
            channel="whatsapp",
            to="+385911234567",
            message_type="image",
            payload={},
        )

    assert result.status == "failed"
    assert result.error_code == "validation_error"
    assert calls == []


def test_requires_credentials() -> None:
    with pytest.raises(ValueError, match="phone_number_id"):
        MetaWhatsAppProvider(phone_number_id="", access_token="tok")
    with pytest.raises(ValueError, match="access_token"):
        MetaWhatsAppProvider(phone_number_id="pn", access_token="")
