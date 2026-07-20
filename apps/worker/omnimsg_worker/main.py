"""Worker: consume outbound queue jobs from Redis (foundation stub)."""

from __future__ import annotations

import logging
import signal
import sys
import time
from types import FrameType

from omnimsg_common.queue import create_redis_client, dequeue_json
from omnimsg_common.settings import get_settings

logger = logging.getLogger(__name__)

_shutdown = False


def _handle_signal(signum: int, _frame: FrameType | None) -> None:
    global _shutdown
    logger.info("received signal %s; shutting down after current poll", signum)
    _shutdown = True


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

    event = job.get("event") if isinstance(job.get("event"), dict) else job
    event_type = event.get("event_type", "unknown")
    data = event.get("data") or {}
    logger.info(
        "processed stub job job_type=%s event_type=%s message_id=%s correlation_id=%s",
        job.get("job_type", "legacy"),
        event_type,
        data.get("message_id"),
        event.get("correlation_id"),
    )
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
        "worker started; queue=%s redis=%s",
        settings.outbound_queue_key,
        settings.redis_url,
    )

    while not _shutdown:
        try:
            processed = run_once(timeout_seconds=5)
            if not processed:
                # brpop already blocked; brief yield for signal responsiveness
                time.sleep(0.05)
        except Exception:  # noqa: BLE001 — keep worker alive on transient Redis errors
            logger.exception("queue poll failed; retrying")
            time.sleep(1)

    logger.info("worker stopped")


def run() -> None:
    main()


if __name__ == "__main__":
    main()
    sys.exit(0)
