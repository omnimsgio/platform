"""API key hashing helpers (plain keys are never stored)."""

from __future__ import annotations

import hashlib
import secrets

API_KEY_PREFIX = "omni_"


def hash_api_key(raw_key: str) -> str:
    """Return a SHA-256 hex digest of the raw API key."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def key_display_prefix(raw_key: str, *, length: int = 12) -> str:
    """Return a short non-secret prefix for operator display / logs."""
    return raw_key[:length]


def generate_api_key() -> str:
    """Generate a new opaque API key (`omni_…`)."""
    return f"{API_KEY_PREFIX}{secrets.token_urlsafe(32)}"


def looks_like_api_key(raw_key: str) -> bool:
    """True if the token matches the expected `omni_…` shape."""
    return raw_key.startswith(API_KEY_PREFIX) and len(raw_key) > len(API_KEY_PREFIX) + 8
