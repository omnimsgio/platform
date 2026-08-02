"""Meta WhatsApp Cloud API adapter (ADR-0004 / ADR-0018)."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from omnimsg_providers.base import SendResult

logger = logging.getLogger(__name__)

DEFAULT_GRAPH_BASE_URL = "https://graph.facebook.com"
DEFAULT_API_VERSION = "v21.0"


class MetaWhatsAppProvider:
    """Sends outbound WhatsApp messages via Meta Graph Cloud API."""

    name = "meta_whatsapp"

    def __init__(
        self,
        *,
        phone_number_id: str,
        access_token: str,
        api_version: str = DEFAULT_API_VERSION,
        base_url: str = DEFAULT_GRAPH_BASE_URL,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not phone_number_id or not str(phone_number_id).strip():
            raise ValueError("phone_number_id is required")
        if not access_token or not str(access_token).strip():
            raise ValueError("access_token is required")
        self._phone_number_id = str(phone_number_id).strip()
        self._access_token = str(access_token).strip()
        self._api_version = api_version.strip().lstrip("/") or DEFAULT_API_VERSION
        self._base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout)

    @property
    def messages_url(self) -> str:
        return (
            f"{self._base_url}/{self._api_version}/{self._phone_number_id}/messages"
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> MetaWhatsAppProvider:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def send(
        self,
        *,
        channel: str,
        to: str,
        message_type: str,
        payload: dict[str, Any],
    ) -> SendResult:
        if channel != "whatsapp":
            return SendResult(
                status="failed",
                provider=self.name,
                error_code="validation_error",
                error_message=f"Unsupported channel for Meta WhatsApp: {channel}",
            )
        if not to or not str(to).strip():
            return SendResult(
                status="failed",
                provider=self.name,
                error_code="validation_error",
                error_message="to is required",
            )

        body, build_error = _build_graph_body(
            to=str(to).strip(),
            message_type=message_type,
            payload=payload if isinstance(payload, dict) else {},
        )
        if build_error is not None:
            return build_error

        try:
            response = self._client.post(
                self.messages_url,
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
        except httpx.RequestError as exc:
            logger.warning("meta whatsapp request failed: %s", exc)
            return SendResult(
                status="failed",
                provider=self.name,
                error_code="upstream_unreachable",
                error_message=str(exc) or "Graph API request failed",
            )

        return _map_graph_response(response)


def _build_graph_body(
    *,
    to: str,
    message_type: str,
    payload: dict[str, Any],
) -> tuple[dict[str, Any] | None, SendResult | None]:
    if message_type != "text":
        return None, SendResult(
            status="failed",
            provider=MetaWhatsAppProvider.name,
            error_code="validation_error",
            error_message=f"Unsupported message type: {message_type}",
        )

    text = payload.get("text") if isinstance(payload.get("text"), dict) else None
    body_text = text.get("body") if text else None
    if not body_text or not str(body_text).strip():
        return None, SendResult(
            status="failed",
            provider=MetaWhatsAppProvider.name,
            error_code="validation_error",
            error_message="text.body is required",
        )

    text_obj: dict[str, Any] = {"body": str(body_text)}
    if "preview_url" in (text or {}):
        text_obj["preview_url"] = bool(text["preview_url"])

    return (
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": _normalize_recipient(to),
            "type": "text",
            "text": text_obj,
        },
        None,
    )


def _normalize_recipient(to: str) -> str:
    """Cloud API accepts digits; strip leading + and whitespace."""
    stripped = to.strip()
    if stripped.startswith("+"):
        return stripped[1:]
    return stripped


def _map_graph_response(response: httpx.Response) -> SendResult:
    try:
        data = response.json()
    except ValueError:
        data = None

    if response.is_success:
        provider_message_id = _extract_message_id(data)
        return SendResult(
            status="accepted",
            provider=MetaWhatsAppProvider.name,
            provider_message_id=provider_message_id,
        )

    error_code, error_message = _extract_error(data, response)
    return SendResult(
        status="failed",
        provider=MetaWhatsAppProvider.name,
        error_code=error_code,
        error_message=error_message,
    )


def _extract_message_id(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    messages = data.get("messages")
    if not isinstance(messages, list) or not messages:
        return None
    first = messages[0]
    if not isinstance(first, dict):
        return None
    message_id = first.get("id")
    return str(message_id) if message_id else None


def _extract_error(data: Any, response: httpx.Response) -> tuple[str, str]:
    if isinstance(data, dict) and isinstance(data.get("error"), dict):
        err = data["error"]
        code = err.get("code")
        message = err.get("message")
        error_code = str(code) if code is not None else "upstream_failure"
        error_message = (
            str(message).strip()
            if message and str(message).strip()
            else f"Graph API error HTTP {response.status_code}"
        )
        return error_code, error_message

    return (
        "upstream_failure",
        f"Graph API error HTTP {response.status_code}",
    )
