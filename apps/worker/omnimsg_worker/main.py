"""Worker: outbound send + inbound Meta status → delivery events."""

from __future__ import annotations

import logging
import signal
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from types import FrameType
from typing import Any

from omnimsg_common.db.models import (
    Conversation,
    ConversationReferral,
    Message,
    TenantWhatsappAccount,
)
from omnimsg_common.db.session import session_scope
from omnimsg_common.ids import new_id
from omnimsg_common.queue import create_redis_client, dequeue_json_any, enqueue_json
from omnimsg_common.settings import get_settings
from omnimsg_common.whatsapp_lifecycle import messaging_ready_statuses
from omnimsg_providers.base import SendResult
from omnimsg_providers.stub import get_default_provider
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from whatsapp import MetaWhatsAppProvider
from whatsapp.referral import extract_referrals

from omnimsg_worker.inbound_persist import persist_inbound_messages_from_webhook

logger = logging.getLogger(__name__)


@dataclass
class ReferralPersistStats:
    """Lightweight referral metrics for one inbound job."""

    detected: int = 0
    persisted: int = 0
    skipped: int = 0
    duplicate: int = 0

_shutdown = False

_META_STATUS_MAP = {
    "sent": "sent",
    "delivered": "delivered",
    "read": "read",
    "failed": "failed",
}


def _handle_signal(signum: int, _frame: FrameType | None) -> None:
    global _shutdown
    logger.info("received signal %s; shutting down after current poll", signum)
    _shutdown = True


def _iso_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_whatsapp_account(tenant_id: str) -> tuple[str, str] | None:
    """Return (phone_number_id, access_token) for a messaging-ready WhatsApp account."""
    ready = messaging_ready_statuses()
    with session_scope() as session:
        row = session.scalars(
            select(TenantWhatsappAccount)
            .where(
                TenantWhatsappAccount.tenant_id == tenant_id,
                TenantWhatsappAccount.status.in_(ready),
            )
            .order_by(TenantWhatsappAccount.created_at.asc())
        ).first()
        if row is None or not row.phone_number_id or not row.business_access_token:
            return None
        return row.phone_number_id, row.business_access_token


def _send_outbound(
    *,
    channel: str,
    tenant_id: str,
    to: str,
    message_type: str,
    payload: dict[str, Any],
) -> SendResult:
    """Route WhatsApp to Meta Cloud API; other channels use the stub provider."""
    if channel == "whatsapp":
        account = _load_whatsapp_account(tenant_id)
        if account is None:
            return SendResult(
                status="failed",
                provider="meta_whatsapp",
                error_code="whatsapp_not_configured",
                error_message="No messaging-ready WhatsApp account configured for tenant",
            )
        phone_number_id, access_token = account
        with MetaWhatsAppProvider(
            phone_number_id=phone_number_id,
            access_token=access_token,
        ) as provider:
            return provider.send(
                channel=channel,
                to=to,
                message_type=message_type,
                payload=payload,
            )

    return get_default_provider().send(
        channel=channel,
        to=to,
        message_type=message_type,
        payload=payload,
    )


def _emit_delivery_updated(
    *,
    tenant_id: str,
    correlation_id: str,
    message_id: str,
    channel: str,
    status: str,
    provider: str | None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    settings = get_settings()
    updated_at = _iso_now()
    delivery_event: dict[str, Any] = {
        "event_id": new_id("evt"),
        "event_type": "message.delivery_updated.v1",
        "occurred_at": updated_at,
        "tenant_id": tenant_id,
        "correlation_id": correlation_id,
        "data": {
            "message_id": message_id,
            "channel": channel,
            "status": status,
            "updated_at": updated_at,
        },
    }
    if provider:
        delivery_event["data"]["provider"] = provider
    if status in {"failed", "undeliverable"}:
        delivery_event["data"]["error"] = {
            "code": error_code or "upstream_failure",
            "message": error_message or "Delivery failed",
            "retryable": False,
            "correlation_id": correlation_id,
        }

    client = create_redis_client(settings)
    try:
        enqueue_json(client, settings.delivery_events_key, delivery_event)
    finally:
        client.close()

    logger.info(
        "delivery updated message_id=%s status=%s provider=%s correlation_id=%s",
        message_id,
        status,
        provider,
        correlation_id,
    )


def process_job(job: dict[str, Any]) -> None:
    """Load message, send via provider, persist status, emit delivery event."""
    event = job.get("event") if isinstance(job.get("event"), dict) else {}
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}

    message_id = data.get("message_id")
    tenant_id = event.get("tenant_id")
    correlation_id = event.get("correlation_id") or new_id("req")
    channel = data.get("channel") or "whatsapp"
    to = data.get("to") or ""
    message_type = payload.get("type") or "text"

    if not message_id or not tenant_id:
        logger.warning("skipping job without message_id/tenant_id: %s", job)
        return

    result = _send_outbound(
        channel=channel,
        tenant_id=str(tenant_id),
        to=to,
        message_type=message_type,
        payload=payload,
    )
    status = result.status if result.status in {"accepted", "failed"} else "failed"

    with session_scope() as session:
        row = session.scalars(
            select(Message).where(
                Message.id == message_id,
                Message.tenant_id == tenant_id,
            )
        ).first()
        if row is None:
            logger.warning(
                "message not found message_id=%s tenant_id=%s",
                message_id,
                tenant_id,
            )
            return
        row.status = status
        row.updated_at = datetime.now(UTC)
        if result.provider_message_id:
            stored = dict(row.payload or {})
            stored["provider_message_id"] = result.provider_message_id
            row.payload = stored
        channel = row.channel

    _emit_delivery_updated(
        tenant_id=str(tenant_id),
        correlation_id=str(correlation_id),
        message_id=str(message_id),
        channel=channel,
        status=status,
        provider=result.provider,
        error_code=result.error_code,
        error_message=result.error_message,
    )


def _extract_status_updates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect Meta ``statuses`` entries from a webhook body."""
    updates: list[dict[str, Any]] = []
    entries = payload.get("entry")
    if not isinstance(entries, list):
        return updates
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
            if not isinstance(statuses, list):
                continue
            for status in statuses:
                if isinstance(status, dict):
                    updates.append(status)
    return updates


def _map_meta_status(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    return _META_STATUS_MAP.get(raw.strip().lower())


def _status_error(status_obj: dict[str, Any]) -> tuple[str | None, str | None]:
    errors = status_obj.get("errors")
    if not isinstance(errors, list) or not errors:
        return None, None
    first = errors[0]
    if not isinstance(first, dict):
        return None, None
    code = first.get("code")
    message = first.get("message") or first.get("title")
    error_code = str(code) if code is not None else "upstream_failure"
    error_message = (
        str(message).strip()
        if message and str(message).strip()
        else "Provider reported delivery failure"
    )
    return error_code, error_message


def _parse_received_at(raw: Any) -> datetime:
    """OmniMsg webhook receive time from envelope; fallback to now UTC."""
    if isinstance(raw, str) and raw.strip():
        text = raw.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed
        except ValueError:
            pass
    return datetime.now(UTC)


def _upsert_conversation(
    *,
    tenant_id: str,
    channel: str,
    provider: str,
    contact_external_id: str,
    phone_number_id: str | None,
) -> str:
    """Insert or reuse conversation; rely on DB uniqueness for races."""
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
    with session_scope() as session:
        return str(session.execute(stmt).scalar_one())


def persist_conversation_referrals(
    *,
    tenant_id: str,
    channel: str,
    provider: str,
    payload: dict[str, Any],
    received_at: datetime,
) -> ReferralPersistStats:
    """Extract and persist CTWA referrals; never raises for parser issues."""
    stats = ReferralPersistStats()
    extracted = extract_referrals(payload, tenant_id=tenant_id)
    stats.detected = extracted.detected
    stats.skipped = extracted.skipped
    referrals = extracted.referrals or []

    for item in referrals:
        try:
            conversation_id = _upsert_conversation(
                tenant_id=tenant_id,
                channel=channel,
                provider=provider,
                contact_external_id=item.contact_external_id,
                phone_number_id=item.phone_number_id,
            )
            referral_id = new_id("cref")
            now = datetime.now(UTC)
            stmt = (
                insert(ConversationReferral)
                .values(
                    id=referral_id,
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    source=item.source,
                    source_id=item.source_id,
                    headline=item.headline,
                    body=item.body,
                    media_type=item.media_type,
                    ctwa_clid=item.ctwa_clid,
                    raw_payload=item.raw_payload,
                    provider_message_id=item.provider_message_id,
                    received_at=received_at,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_nothing(
                    constraint="uq_conversation_referrals_tenant_provider_message"
                )
                .returning(ConversationReferral.id)
            )
            with session_scope() as session:
                inserted_id = session.execute(stmt).scalar_one_or_none()
                if inserted_id:
                    stats.persisted += 1
                else:
                    stats.duplicate += 1
        except Exception:  # noqa: BLE001 — isolate per-message persist errors
            stats.skipped += 1
            logger.warning(
                "referral_skipped tenant_id=%s provider_message_id=%s reason=%s",
                tenant_id,
                item.provider_message_id,
                "persist_failed",
                exc_info=True,
            )

    logger.info(
        "metric referrals_detected=%s referrals_persisted=%s "
        "referrals_skipped=%s referrals_duplicate=%s tenant_id=%s",
        stats.detected,
        stats.persisted,
        stats.skipped,
        stats.duplicate,
        tenant_id,
    )
    return stats


def process_inbound_job(job: dict[str, Any]) -> ReferralPersistStats | None:
    """Handle inbound webhook jobs; persist referrals then message_status updates."""
    event = job.get("event") if isinstance(job.get("event"), dict) else {}
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}

    tenant_id = event.get("tenant_id")
    correlation_id = event.get("correlation_id") or new_id("req")
    kind = data.get("kind")
    provider = data.get("provider") or "meta_whatsapp"
    channel = data.get("channel") or "whatsapp"

    if not tenant_id:
        logger.warning("skipping inbound job without tenant_id: %s", job)
        return None

    referral_stats: ReferralPersistStats | None = None
    try:
        referral_stats = persist_conversation_referrals(
            tenant_id=str(tenant_id),
            channel=str(channel),
            provider=str(provider),
            payload=payload,
            received_at=_parse_received_at(data.get("received_at")),
        )
    except Exception:  # noqa: BLE001 — referral path must not block status updates
        logger.error(
            "referral_persist_failed tenant_id=%s provider_message_id=%s reason=%s",
            tenant_id,
            "-",
            "unexpected_persist_error",
            exc_info=True,
        )

    if kind == "inbound_message":
        try:
            inbound_stats = persist_inbound_messages_from_webhook(
                tenant_id=str(tenant_id),
                channel=str(channel),
                provider=str(provider),
                correlation_id=str(correlation_id),
                payload=payload,
                received_at=(
                    data.get("received_at")
                    if isinstance(data.get("received_at"), str)
                    else None
                ),
            )
            logger.info(
                "inbound_message persisted inserted=%s duplicate=%s "
                "skipped=%s tenant_id=%s correlation_id=%s",
                inbound_stats.inserted,
                inbound_stats.duplicate,
                inbound_stats.skipped,
                tenant_id,
                correlation_id,
            )
        except Exception:  # noqa: BLE001 — must not block other paths
            logger.error(
                "inbound_message_persist_failed tenant_id=%s correlation_id=%s",
                tenant_id,
                correlation_id,
                exc_info=True,
            )
        return referral_stats

    if kind != "message_status":
        logger.info(
            "inbound job kind=%s status_path_skipped tenant_id=%s correlation_id=%s",
            kind,
            tenant_id,
            correlation_id,
        )
        return referral_stats

    updates = _extract_status_updates(payload)
    if not updates:
        logger.info(
            "message_status job had no statuses tenant_id=%s correlation_id=%s",
            tenant_id,
            correlation_id,
        )
        return referral_stats

    for status_obj in updates:
        provider_message_id = status_obj.get("id")
        mapped = _map_meta_status(status_obj.get("status"))
        if not isinstance(provider_message_id, str) or not provider_message_id.strip():
            logger.warning("skipping status update without id: %s", status_obj)
            continue
        if mapped is None:
            logger.info(
                "skipping unmapped meta status=%s id=%s",
                status_obj.get("status"),
                provider_message_id,
            )
            continue

        provider_message_id = provider_message_id.strip()
        error_code, error_message = (
            _status_error(status_obj) if mapped == "failed" else (None, None)
        )

        with session_scope() as session:
            row = session.scalars(
                select(Message).where(
                    Message.tenant_id == tenant_id,
                    Message.payload["provider_message_id"].astext == provider_message_id,
                )
            ).first()
            if row is None:
                logger.warning(
                    "no message for provider_message_id=%s tenant_id=%s",
                    provider_message_id,
                    tenant_id,
                )
                continue
            row.status = mapped
            row.updated_at = datetime.now(UTC)
            message_id = row.id
            channel = row.channel

        _emit_delivery_updated(
            tenant_id=str(tenant_id),
            correlation_id=str(correlation_id),
            message_id=message_id,
            channel=channel,
            status=mapped,
            provider=str(provider) if provider else None,
            error_code=error_code,
            error_message=error_message,
        )

    return referral_stats


def run_once(timeout_seconds: int = 1) -> bool:
    """Poll outbound + inbound once; return True if a job was processed."""
    settings = get_settings()
    client = create_redis_client(settings)
    try:
        item = dequeue_json_any(
            client,
            [settings.outbound_queue_key, settings.inbound_queue_key],
            timeout_seconds=timeout_seconds,
        )
    finally:
        client.close()

    if item is None:
        return False

    queue_key, job = item
    if queue_key == settings.inbound_queue_key:
        process_inbound_job(job)
    else:
        process_job(job)
    return True


def main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    logger.info(
        "worker started; outbound=%s inbound=%s events=%s redis=%s",
        settings.outbound_queue_key,
        settings.inbound_queue_key,
        settings.delivery_events_key,
        settings.redis_url,
    )

    while not _shutdown:
        try:
            processed = run_once(timeout_seconds=5)
            if not processed:
                time.sleep(0.05)
        except Exception:  # noqa: BLE001 — keep worker alive on transient errors
            logger.exception("queue poll failed; retrying")
            time.sleep(1)

    logger.info("worker stopped")


def run() -> None:
    main()


if __name__ == "__main__":
    main()
    sys.exit(0)
