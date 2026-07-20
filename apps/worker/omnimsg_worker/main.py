"""Worker: execution-engine stub — status update + delivery events."""

from __future__ import annotations

import logging
import signal
import sys
import time
from datetime import UTC, datetime
from types import FrameType
from typing import Any

from omnimsg_common.db.models import Message
from omnimsg_common.db.session import session_scope
from omnimsg_common.ids import new_id
from omnimsg_common.queue import create_redis_client, dequeue_json, enqueue_json
from omnimsg_common.settings import get_settings
from omnimsg_providers.stub import get_default_provider
from sqlalchemy import select

logger = logging.getLogger(__name__)

_shutdown = False


def _handle_signal(signum: int, _frame: FrameType | None) -> None:
    global _shutdown
    logger.info("received signal %s; shutting down after current poll", signum)
    _shutdown = True


def _iso_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def process_job(job: dict[str, Any]) -> None:
    """Load message, stub-send via provider ABC, persist status, emit event."""
    settings = get_settings()
    provider = get_default_provider()

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

    result = provider.send(
        channel=channel,
        to=to,
        message_type=message_type,
        payload=payload,
    )
    status = result.status if result.status in {"accepted", "failed"} else "failed"
    updated_at = _iso_now()

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
        channel = row.channel
        to = row.to

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
            "provider": result.provider,
        },
    }
    if status == "failed":
        delivery_event["data"]["error"] = {
            "code": result.error_code or "upstream_failure",
            "message": result.error_message or "Delivery failed",
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
        result.provider,
        correlation_id,
    )


def run_once(timeout_seconds: int = 1) -> bool:
    """Poll once; return True if a job was processed."""
    settings = get_settings()
    client = create_redis_client(settings)
    try:
        job = dequeue_json(
            client,
            settings.outbound_queue_key,
            timeout_seconds=timeout_seconds,
        )
    finally:
        client.close()

    if job is None:
        return False

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
        "worker started; queue=%s events=%s redis=%s",
        settings.outbound_queue_key,
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
