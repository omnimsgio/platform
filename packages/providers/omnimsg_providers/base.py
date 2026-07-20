"""Provider adapter protocol (ADR-0004)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class SendResult:
    """Normalized result from a provider send attempt."""

    status: str  # accepted | failed
    provider: str
    error_code: str | None = None
    error_message: str | None = None


@runtime_checkable
class MessageProvider(Protocol):
    """Thin channel adapter interface used by the execution engine."""

    name: str

    def send(
        self,
        *,
        channel: str,
        to: str,
        message_type: str,
        payload: dict[str, Any],
    ) -> SendResult:
        """Send (or stub-send) an outbound message via the vendor."""
        ...
