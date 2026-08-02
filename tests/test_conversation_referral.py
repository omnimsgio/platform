"""Integration: ConversationReferral persistence from inbound Meta webhooks."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from omnimsg_common.db.models import (
    Conversation,
    ConversationReferral,
    Message,
    TenantWhatsappAccount,
)
from omnimsg_common.db.session import session_scope
from omnimsg_common.ids import new_id
from omnimsg_common.queue import create_redis_client
from omnimsg_common.settings import get_settings
from omnimsg_common.whatsapp_lifecycle import READY, bootstrap_ready
from omnimsg_worker.main import process_inbound_job
from sqlalchemy import func, select


@pytest.fixture
def seeded_whatsapp(seeded_tenant: dict[str, str]) -> dict[str, str]:
    account_id = new_id("wa")
    phone_number_id = "pn_ref_test_123"
    with session_scope() as session:
        account = TenantWhatsappAccount(
            id=account_id,
            tenant_id=seeded_tenant["tenant_id"],
            waba_id="waba_test",
            phone_number_id=phone_number_id,
            business_access_token="tok_test_business",
            credit_line_attached=False,
            status=READY,
            lifecycle_version=1,
        )
        session.add(account)
        bootstrap_ready(account, correlation_id="req_seed_ref")
    return {
        **seeded_tenant,
        "whatsapp_account_id": account_id,
        "phone_number_id": phone_number_id,
    }


@pytest.fixture
def redis_client(seeded_tenant: dict[str, str]):
    del seeded_tenant
    settings = get_settings()
    client = create_redis_client(settings)
    try:
        client.ping()
    except Exception as exc:  # noqa: BLE001
        client.close()
        pytest.skip(f"Redis not available: {exc}")
    for key in client.scan_iter(match=f"{settings.redis_key_prefix}*"):
        client.delete(key)
    yield client
    for key in client.scan_iter(match=f"{settings.redis_key_prefix}*"):
        client.delete(key)
    client.close()


def _referral_obj(*, clid: str, extra: dict | None = None) -> dict:
    body = {
        "source": "AD",
        "source_id": "120000000000000000",
        "headline": "Offer",
        "body": "Click",
        "media_type": "image",
        "ctwa_clid": clid,
    }
    if extra:
        body.update(extra)
    return body


def _inbound_job(
    *,
    tenant_id: str,
    phone_number_id: str,
    messages: list[dict],
    kind: str = "inbound_message",
    received_at: str = "2026-08-02T10:00:00Z",
    statuses: list[dict] | None = None,
) -> dict:
    value: dict = {
        "metadata": {"phone_number_id": phone_number_id},
        "messages": messages,
    }
    if statuses is not None:
        value["statuses"] = statuses
    return {
        "job_type": "inbound_webhook",
        "event": {
            "event_type": "webhook.inbound.received.v1",
            "tenant_id": tenant_id,
            "correlation_id": "req_ref_test",
            "data": {
                "provider": "meta_whatsapp",
                "channel": "whatsapp",
                "kind": kind,
                "payload_ref": "wh_ref",
                "received_at": received_at,
            },
        },
        "payload": {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "WABA",
                    "changes": [{"field": "messages", "value": value}],
                }
            ],
        },
    }


def test_persist_ctwa_referral(seeded_whatsapp: dict[str, str]) -> None:
    job = _inbound_job(
        tenant_id=seeded_whatsapp["tenant_id"],
        phone_number_id=seeded_whatsapp["phone_number_id"],
        messages=[
            {
                "id": "wamid.CTWA_1",
                "from": "385911000001",
                "timestamp": "1720000000",
                "type": "text",
                "referral": _referral_obj(clid="clid_1", extra={"new_field": 1}),
            }
        ],
    )
    stats = process_inbound_job(job)
    assert stats is not None
    assert stats.detected == 1
    assert stats.persisted == 1
    assert stats.skipped == 0
    assert stats.duplicate == 0

    with session_scope() as session:
        convs = list(session.scalars(select(Conversation)).all())
        refs = list(session.scalars(select(ConversationReferral)).all())
        assert len(convs) == 1
        assert len(refs) == 1
        assert refs[0].conversation_id == convs[0].id
        assert refs[0].ctwa_clid == "clid_1"
        assert refs[0].raw_payload["new_field"] == 1
        assert refs[0].provider_message_id == "wamid.CTWA_1"
        assert refs[0].received_at == datetime(2026, 8, 2, 10, 0, tzinfo=UTC)


def test_duplicate_referral_idempotent(seeded_whatsapp: dict[str, str]) -> None:
    job = _inbound_job(
        tenant_id=seeded_whatsapp["tenant_id"],
        phone_number_id=seeded_whatsapp["phone_number_id"],
        messages=[
            {
                "id": "wamid.CTWA_DUP",
                "from": "385911000002",
                "referral": _referral_obj(clid="clid_dup"),
            }
        ],
    )
    first = process_inbound_job(job)
    second = process_inbound_job(job)
    assert first is not None and first.persisted == 1
    assert second is not None
    assert second.detected == 1
    assert second.persisted == 0
    assert second.duplicate == 1

    with session_scope() as session:
        assert session.scalar(select(func.count()).select_from(Conversation)) == 1
        assert session.scalar(select(func.count()).select_from(ConversationReferral)) == 1


def test_inbound_without_referral_preserves_pre_slice_behavior(
    seeded_whatsapp: dict[str, str],
    redis_client,
) -> None:
    """Quality gate: plain inbound invents no ConversationReferral (ADR-0019 freeze).

    P3 may create Conversation + inbound Message; must not invent referrals.
    message_status still updates outbound Message + emits delivery; no referrals.
    """
    settings = get_settings()
    tenant_id = seeded_whatsapp["tenant_id"]
    phone_number_id = seeded_whatsapp["phone_number_id"]

    plain = process_inbound_job(
        _inbound_job(
            tenant_id=tenant_id,
            phone_number_id=phone_number_id,
            kind="inbound_message",
            messages=[{"id": "wamid.PLAIN", "from": "385911000003", "type": "text"}],
        )
    )
    assert plain is not None
    assert plain.detected == 0
    assert plain.persisted == 0
    assert plain.skipped == 0
    assert plain.duplicate == 0

    with session_scope() as session:
        assert session.scalar(select(func.count()).select_from(ConversationReferral)) == 0
        assert session.scalar(select(func.count()).select_from(Conversation)) == 1
        assert (
            session.scalar(
                select(func.count()).select_from(Message).where(Message.direction == "inbound")
            )
            == 1
        )

    delivery_events = [
        json.loads(raw)
        for raw in redis_client.lrange(settings.delivery_events_key, 0, -1)
    ]
    assert all(
        evt.get("event_type") != "message.delivery_updated.v1" for evt in delivery_events
    )
    inbound_events = [
        evt
        for evt in delivery_events
        if evt.get("event_type") == "message.inbound.received.v1"
    ]
    assert len(inbound_events) == 1

    message_id = new_id("msg")
    provider_message_id = "wamid.STATUS_NO_REF"
    with session_scope() as session:
        session.add(
            Message(
                id=message_id,
                tenant_id=tenant_id,
                channel="whatsapp",
                direction="outbound",
                to="+385911234567",
                type="text",
                status="accepted",
                idempotency_key=None,
                correlation_id="req_no_ref_status",
                payload={
                    "type": "text",
                    "text": {"body": "hi"},
                    "provider_message_id": provider_message_id,
                },
            )
        )

    status_stats = process_inbound_job(
        _inbound_job(
            tenant_id=tenant_id,
            phone_number_id=phone_number_id,
            kind="message_status",
            messages=[],
            statuses=[
                {
                    "id": provider_message_id,
                    "status": "delivered",
                    "recipient_id": "385911234567",
                }
            ],
        )
    )
    assert status_stats is not None
    assert status_stats.detected == 0
    assert status_stats.persisted == 0

    with session_scope() as session:
        row = session.scalars(select(Message).where(Message.id == message_id)).first()
        assert row is not None
        assert row.status == "delivered"
        assert session.scalar(select(func.count()).select_from(ConversationReferral)) == 0

    events = [
        json.loads(raw)
        for raw in redis_client.lrange(settings.delivery_events_key, 0, -1)
    ]
    delivery = [e for e in events if e.get("event_type") == "message.delivery_updated.v1"]
    assert len(delivery) == 1
    assert delivery[0]["data"]["status"] == "delivered"


def test_partial_success_batch(seeded_whatsapp: dict[str, str]) -> None:
    job = _inbound_job(
        tenant_id=seeded_whatsapp["tenant_id"],
        phone_number_id=seeded_whatsapp["phone_number_id"],
        messages=[
            {
                "id": "wamid.OK_1",
                "from": "385911000010",
                "referral": _referral_obj(clid="clid_a"),
            },
            {
                "id": "wamid.BAD",
                "from": "385911000011",
                "referral": "invalid",
            },
            {
                "id": "wamid.OK_2",
                "from": "385911000012",
                "referral": _referral_obj(clid="clid_b"),
            },
        ],
    )
    stats = process_inbound_job(job)
    assert stats is not None
    assert stats.detected == 3
    assert stats.persisted == 2
    assert stats.skipped == 1

    with session_scope() as session:
        assert session.scalar(select(func.count()).select_from(ConversationReferral)) == 2
        # Three contacts (including invalid referral) still get Conversation via P3 inbound persist.
        assert session.scalar(select(func.count()).select_from(Conversation)) == 3
        assert (
            session.scalar(
                select(func.count()).select_from(Message).where(Message.direction == "inbound")
            )
            == 3
        )


def test_concurrent_identical_jobs(seeded_whatsapp: dict[str, str]) -> None:
    job = _inbound_job(
        tenant_id=seeded_whatsapp["tenant_id"],
        phone_number_id=seeded_whatsapp["phone_number_id"],
        messages=[
            {
                "id": "wamid.CTWA_RACE",
                "from": "385911000020",
                "referral": _referral_obj(clid="clid_race"),
            }
        ],
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(process_inbound_job, job) for _ in range(2)]
        results = [f.result() for f in futures]

    assert all(r is not None for r in results)
    assert sum(r.persisted for r in results if r is not None) == 1
    assert sum(r.duplicate for r in results if r is not None) == 1

    with session_scope() as session:
        assert session.scalar(select(func.count()).select_from(Conversation)) == 1
        assert session.scalar(select(func.count()).select_from(ConversationReferral)) == 1


def test_referral_failure_does_not_block_status(
    seeded_whatsapp: dict[str, str],
    redis_client,
) -> None:
    settings = get_settings()
    message_id = new_id("msg")
    provider_message_id = "wamid.STATUS_WITH_REF"
    with session_scope() as session:
        session.add(
            Message(
                id=message_id,
                tenant_id=seeded_whatsapp["tenant_id"],
                channel="whatsapp",
                to="+385911234567",
                type="text",
                status="accepted",
                idempotency_key=None,
                correlation_id="req_ref_status",
                payload={
                    "type": "text",
                    "text": {"body": "hi"},
                    "provider_message_id": provider_message_id,
                },
            )
        )

    job = _inbound_job(
        tenant_id=seeded_whatsapp["tenant_id"],
        phone_number_id=seeded_whatsapp["phone_number_id"],
        kind="message_status",
        messages=[
            {
                "id": "wamid.IGNORED_IN_STATUS",
                "from": "385911000099",
                "referral": _referral_obj(clid="clid_status"),
            }
        ],
        statuses=[
            {
                "id": provider_message_id,
                "status": "delivered",
                "recipient_id": "385911234567",
            }
        ],
    )

    with patch(
        "omnimsg_worker.main.persist_conversation_referrals",
        side_effect=RuntimeError("boom"),
    ):
        process_inbound_job(job)

    with session_scope() as session:
        row = session.scalars(select(Message).where(Message.id == message_id)).first()
        assert row is not None
        assert row.status == "delivered"

    events = redis_client.lrange(settings.delivery_events_key, 0, -1)
    assert len(events) == 1
