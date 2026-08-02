"""Meta WhatsApp Cloud API webhook helpers (verify + normalize)."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any


def verify_meta_signature(*, app_secret: str, body: bytes, signature_header: str | None) -> bool:
    """Validate ``X-Hub-Signature-256: sha256=<hex>`` against the raw body."""
    if not app_secret or not signature_header:
        return False
    prefix = "sha256="
    if not signature_header.startswith(prefix):
        return False
    provided = signature_header[len(prefix) :].strip()
    if not provided:
        return False
    digest = hmac.new(
        app_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(digest, provided)


def extract_phone_number_id(payload: dict[str, Any]) -> str | None:
    """Return the first ``metadata.phone_number_id`` from a Meta WhatsApp webhook."""
    entries = payload.get("entry")
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        changes = entry.get("changes")
        if not isinstance(changes, list):
            continue
        for change in changes:
            if not isinstance(change, dict):
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            metadata = value.get("metadata")
            if not isinstance(metadata, dict):
                continue
            phone_number_id = metadata.get("phone_number_id")
            if isinstance(phone_number_id, str) and phone_number_id.strip():
                return phone_number_id.strip()
    return None


def classify_webhook_kind(payload: dict[str, Any]) -> str:
    """Map Meta payload shape to ``webhook.inbound.received.v1`` kind."""
    entries = payload.get("entry")
    if not isinstance(entries, list):
        return "unknown"
    saw_status = False
    saw_message = False
    saw_account = False
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        changes = entry.get("changes")
        if not isinstance(changes, list):
            continue
        for change in changes:
            if not isinstance(change, dict):
                continue
            field = change.get("field")
            if field in {"account_update", "account_review_update", "business_capability_update"}:
                saw_account = True
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            if isinstance(value.get("statuses"), list) and value["statuses"]:
                saw_status = True
            if isinstance(value.get("messages"), list) and value["messages"]:
                saw_message = True
    if saw_status:
        return "message_status"
    if saw_message:
        return "inbound_message"
    if saw_account:
        return "account_update"
    return "unknown"


def extract_external_event_id(payload: dict[str, Any]) -> str | None:
    """Best-effort provider event/message id from the first status or message."""
    entries = payload.get("entry")
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        changes = entry.get("changes")
        if not isinstance(changes, list):
            continue
        for change in changes:
            if not isinstance(change, dict):
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            statuses = value.get("statuses")
            if isinstance(statuses, list):
                for status in statuses:
                    if isinstance(status, dict):
                        for key in ("id", "gs_id"):
                            raw = status.get(key)
                            if isinstance(raw, str) and raw.strip():
                                return raw.strip()
            messages = value.get("messages")
            if isinstance(messages, list):
                for message in messages:
                    if isinstance(message, dict):
                        raw = message.get("id")
                        if isinstance(raw, str) and raw.strip():
                            return raw.strip()
    return None


def parse_webhook_json(body: bytes) -> dict[str, Any] | None:
    """Parse webhook body as a JSON object; None if invalid."""
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def webhook_payload_redis_key(*, redis_key_prefix: str, payload_id: str) -> str:
    """Redis key for a stored raw webhook payload (``payload_ref``)."""
    prefix = redis_key_prefix
    if not prefix.endswith(":"):
        prefix = f"{prefix}:"
    return f"{prefix}webhook:payload:{payload_id}"
