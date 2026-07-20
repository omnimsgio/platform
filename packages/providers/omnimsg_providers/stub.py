"""No-op / stub provider used until the channels phase wires real vendors."""

from __future__ import annotations

from typing import Any

from omnimsg_providers.base import MessageProvider, SendResult


class StubMessageProvider:
    """Accepts valid text payloads; fails when text body is missing."""

    name = "stub"

    def send(
        self,
        *,
        channel: str,
        to: str,
        message_type: str,
        payload: dict[str, Any],
    ) -> SendResult:
        del channel, to  # unused in stub; kept for interface parity
        if message_type != "text":
            return SendResult(
                status="failed",
                provider=self.name,
                error_code="validation_error",
                error_message=f"Unsupported message type: {message_type}",
            )
        text = payload.get("text") if isinstance(payload, dict) else None
        body = text.get("body") if isinstance(text, dict) else None
        if not body or not str(body).strip():
            return SendResult(
                status="failed",
                provider=self.name,
                error_code="validation_error",
                error_message="text.body is required",
            )
        return SendResult(status="accepted", provider=self.name)


def get_default_provider() -> MessageProvider:
    return StubMessageProvider()
