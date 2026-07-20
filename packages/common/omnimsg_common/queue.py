"""Redis list queue helpers (shared Redis DB 3, key prefix omnimsgio:)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import redis

from omnimsg_common.settings import Settings


def create_redis_client(settings: Settings) -> redis.Redis:
    """Create a Redis client from settings (decode responses as str)."""
    return redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=5,
        # None so BRPOP can block longer than the default 5s socket timeout.
        socket_timeout=None,
    )


def enqueue_json(client: redis.Redis, queue_key: str, payload: dict[str, Any]) -> None:
    """Push a JSON job onto the left of a Redis list."""
    client.lpush(queue_key, json.dumps(payload, separators=(",", ":")))


def dequeue_json(
    client: redis.Redis,
    queue_key: str,
    *,
    timeout_seconds: int = 5,
) -> dict[str, Any] | None:
    """Blocking pop from the right of a Redis list; None on timeout."""
    item = client.brpop(queue_key, timeout=timeout_seconds)
    if item is None:
        return None
    _key, raw = item
    return json.loads(raw)


def dequeue_json_any(
    client: redis.Redis,
    queue_keys: Sequence[str],
    *,
    timeout_seconds: int = 5,
) -> tuple[str, dict[str, Any]] | None:
    """Blocking pop from the first non-empty queue (key order = priority)."""
    keys = [key for key in queue_keys if key]
    if not keys:
        return None
    item = client.brpop(list(keys), timeout=timeout_seconds)
    if item is None:
        return None
    key, raw = item
    return str(key), json.loads(raw)
