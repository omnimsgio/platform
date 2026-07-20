"""Worker: outbound send + inbound Meta status → delivery events."""

from __future__ import annotations

import logging
import signal
import sys
import time
from datetime import UTC, datetime
from types import FrameType
from typing import Any

from omnimsg_common.db.models import Message, TenantWhatsappAccount
from omnimsg_common.db.session import session_scope
from omnimsg_common.ids import new_id
from omnimsg_common.queue import create_redis_client, dequeue_json_any, enqueue_json
from omnimsg_common.settings import get_settings
from omnimsg_providers.base import SendResult
from omnimsg_providers.stub import get_default_provider
from sqlalchemy import select
from whatsapp import MetaWhatsAppProvider

logger = logging.getLogger(__name__)

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
    """Return (phone_number_id, access_token) for an active WhatsApp account."""
    with session_scope() as session:
        row = session.scalars(
            select(TenantWhatsappAccount)
            .where(
                TenantWhatsappAccount.tenant_id == tenant_id,
                TenantWhatsappAccount.status == "active",
            )
            .order_by(TenantWhatsappAccount.created_at.asc())
        ).first()
        if row is None:
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
                error_message="No active WhatsApp account configured for tenant",
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


def process_inbound_job(job: dict[str, Any]) -> None:
    """Handle inbound webhook jobs; apply message_status updates."""
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
        return

    if kind != "message_status":
        logger.info(
            "inbound job kind=%s ignored (no-op) tenant_id=%s correlation_id=%s",
            kind,
            tenant_id,
            correlation_id,
        )
        return

    updates = _extract_status_updates(payload)
    if not updates:
        logger.info(
            "message_status job had no statuses tenant_id=%s correlation_id=%s",
            tenant_id,
            correlation_id,
        )
        return

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
