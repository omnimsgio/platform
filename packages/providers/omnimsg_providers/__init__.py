"""Provider adapter protocol (ADR-0004). Channels phase replaces stub impls."""

from __future__ import annotations

from omnimsg_providers.base import MessageProvider, SendResult
from omnimsg_providers.stub import StubMessageProvider, get_default_provider

__all__ = [
    "MessageProvider",
    "SendResult",
    "StubMessageProvider",
    "get_default_provider",
]
