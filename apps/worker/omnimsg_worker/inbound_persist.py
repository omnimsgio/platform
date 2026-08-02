"""Inbound WhatsApp message persistence (P3) — atomic Conversation + Message."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from omnimsg_common.db.models import Conversation, Message
from omnimsg_common.db.session import session_scope
from omnimsg_common.ids import new_id
from omnimsg_common.queue import create_redis_client, enqueue_json
from omnimsg_common.settings import Settings, get_settings
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InboundPersistResult:
    message_id: str
    conversation_id: str
    provider_message_id: str
    inserted: bool
    message_type: str
    from_address: str
    text_preview: str | None


@dataclass
class InboundPersistStats:
    attempted: int = 0
    inserted: int = 0
    duplicate: int = 0
    skipped: int = 0


def _iso_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _iter_meta_messages(payload: dict[str, Any]) -> list[tuple[dict[str, Any], str | None]]:
    """Yield (message, phone_number_id) from a Meta webhook body."""
    out: list[tuple[dict[str, Any], str | None]] = []
    entries = payload.get("entry")
    if not isinstance(entries, list):
        return out
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
            phone_number_id: str | None = None
            if isinstance(metadata, dict):
                raw_pn = metadata.get("phone_number_id")
                if isinstance(raw_pn, str) and raw_pn.strip():
                    phone_number_id = raw_pn.strip()
            messages = value.get("messages")
            if not isinstance(messages, list):
                continue
            for message in messages:
                if isinstance(message, dict):
                    out.append((message, phone_number_id))
    return out


def _text_preview(message: dict[str, Any]) -> str | None:
    text = message.get("text")
    if isinstance(text, dict):
        body = text.get("body")
        if isinstance(body, str) and body.strip():
            return body.strip()[:512]
    return None


def _normalize_payload(
    *,
    message: dict[str, Any],
    phone_number_id: str | None,
    message_type: str,
) -> dict[str, Any]:
    return {
        "meta_message": message,
        "type": message_type,
        "text": message.get("text") if isinstance(message.get("text"), dict) else None,
        "phone_number_id": phone_number_id,
    }


def upsert_conversation_in_session(
    session: Session,
    *,
    tenant_id: str,
    channel: str,
    provider: str,
    contact_external_id: str,
    phone_number_id: str | None,
) -> str:
    """Upsert by canonical P3 key (tenant, channel, contact_external_id)."""
    conversation_id = new_id("conv")
    now = datetime.now(UTC)
    update_fields: dict[str, Any] = {"updated_at": now}
    if phone_number_id:
        update_fields["phone_number_id"] = phone_number_id
    stmt = (
        insert(Conversation)
        .values(
            id=conversation_id,
            tenant_id=tenant_id,
            channel=channel,
            provider=provider,
            contact_external_id=contact_external_id,
            phone_number_id=phone_number_id,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_update(
            constraint="uq_conversations_tenant_channel_contact",
            set_=update_fields,
        )
        .returning(Conversation.id)
    )
    return str(session.execute(stmt).scalar_one())


def persist_inbound_message(
    *,
    tenant_id: str,
    channel: str,
    provider: str,
    correlation_id: str,
    message: dict[str, Any],
    phone_number_id: str | None,
) -> InboundPersistResult | None:
    """Persist one inbound Meta message atomically with its Conversation.

    Returns None when the message lacks required id/from. On unique conflict,
    returns inserted=False without rewriting payload (immutable audit row).
    """
    provider_message_id = message.get("id")
    from_address = message.get("from")
    if not isinstance(provider_message_id, str) or not provider_message_id.strip():
        return None
    if not isinstance(from_address, str) or not from_address.strip():
        return None
    provider_message_id = provider_message_id.strip()
    from_address = from_address.strip()
    raw_type = message.get("type")
    message_type = (
        raw_type.strip()
        if isinstance(raw_type, str) and raw_type.strip()
        else "unknown"
    )
    to_address = (phone_number_id or "").strip() or "unknown"
    message_id = new_id("msg")
    now = datetime.now(UTC)
    row_payload = _normalize_payload(
        message=message,
        phone_number_id=phone_number_id,
        message_type=message_type,
    )

    with session_scope() as session:
        conversation_id = upsert_conversation_in_session(
            session,
            tenant_id=tenant_id,
            channel=channel,
            provider=provider,
            contact_external_id=from_address,
            phone_number_id=phone_number_id,
        )
        stmt = (
            insert(Message)
            .values(
                id=message_id,
                tenant_id=tenant_id,
                channel=channel,
                direction="inbound",
                to=to_address,
                from_address=from_address,
                type=message_type[:32],
                status="received",
                idempotency_key=None,
                correlation_id=correlation_id,
                conversation_id=conversation_id,
                provider_message_id=provider_message_id,
                payload=row_payload,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "provider_message_id"],
                index_where=text("provider_message_id IS NOT NULL"),
            )
            .returning(Message.id, Message.conversation_id)
        )
        row = session.execute(stmt).one_or_none()
        if row is None:
            existing = session.scalars(
                select(Message).where(
                    Message.tenant_id == tenant_id,
                    Message.provider_message_id == provider_message_id,
                )
            ).one()
            return InboundPersistResult(
                message_id=existing.id,
                conversation_id=existing.conversation_id or conversation_id,
                provider_message_id=provider_message_id,
                inserted=False,
                message_type=existing.type,
                from_address=existing.from_address or from_address,
                text_preview=_text_preview(message),
            )
        return InboundPersistResult(
            message_id=str(row[0]),
            conversation_id=str(row[1]),
            provider_message_id=provider_message_id,
            inserted=True,
            message_type=message_type[:32],
            from_address=from_address,
            text_preview=_text_preview(message),
        )


def emit_inbound_received(
    *,
    tenant_id: str,
    correlation_id: str,
    result: InboundPersistResult,
    channel: str,
    received_at: str | None = None,
    settings: Settings | None = None,
) -> None:
    """Emit message.inbound.received.v1 only after a successful new insert + COMMIT."""
    if not result.inserted:
        return
    settings = settings or get_settings()
    occurred_at = received_at or _iso_now()
    event = {
        "event_id": new_id("evt"),
        "event_type": "message.inbound.received.v1",
        "occurred_at": occurred_at,
        "tenant_id": tenant_id,
        "correlation_id": correlation_id,
        "data": {
            "message_id": result.message_id,
            "conversation_id": result.conversation_id,
            "channel": channel,
            "provider_message_id": result.provider_message_id,
            "from": result.from_address,
            "received_at": occurred_at,
            "type": result.message_type,
            "text": result.text_preview,
        },
    }
    client = create_redis_client(settings)
    try:
        enqueue_json(client, settings.delivery_events_key, event)
    finally:
        client.close()
    logger.info(
        "inbound received message_id=%s conversation_id=%s "
        "provider_message_id=%s correlation_id=%s",
        result.message_id,
        result.conversation_id,
        result.provider_message_id,
        correlation_id,
    )


def persist_inbound_messages_from_webhook(
    *,
    tenant_id: str,
    channel: str,
    provider: str,
    correlation_id: str,
    payload: dict[str, Any],
    received_at: str | None = None,
) -> InboundPersistStats:
    """Persist all inbound messages; emit events only after successful inserts."""
    stats = InboundPersistStats()
    for message, phone_number_id in _iter_meta_messages(payload):
        stats.attempted += 1
        try:
            result = persist_inbound_message(
                tenant_id=tenant_id,
                channel=channel,
                provider=provider,
                correlation_id=correlation_id,
                message=message,
                phone_number_id=phone_number_id,
            )
        except Exception:  # noqa: BLE001 — isolate per-message failures
            stats.skipped += 1
            logger.warning(
                "inbound_persist_failed tenant_id=%s correlation_id=%s",
                tenant_id,
                correlation_id,
                exc_info=True,
            )
            continue
        if result is None:
            stats.skipped += 1
            continue
        if result.inserted:
            stats.inserted += 1
            emit_inbound_received(
                tenant_id=tenant_id,
                correlation_id=correlation_id,
                result=result,
                channel=channel,
                received_at=received_at,
            )
        else:
            stats.duplicate += 1
    logger.info(
        "metric inbound_attempted=%s inbound_inserted=%s "
        "inbound_duplicate=%s inbound_skipped=%s tenant_id=%s correlation_id=%s",
        stats.attempted,
        stats.inserted,
        stats.duplicate,
        stats.skipped,
        tenant_id,
        correlation_id,
    )
    return stats
