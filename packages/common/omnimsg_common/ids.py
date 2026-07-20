"""Opaque platform identifiers for foundation stubs."""

from __future__ import annotations

import uuid


def new_id(prefix: str) -> str:
    """Return a prefixed opaque id (e.g. msg_..., req_..., evt_...)."""
    return f"{prefix}_{uuid.uuid4().hex}"
