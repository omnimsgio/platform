"""P3 inbound message persistence + thread API."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from omnimsg_common.db.models import Conversation, Message, TenantWhatsappAccount
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
    phone_number_id = "pn_inbound_p3"
    with session_scope() as session:
        account = TenantWhatsappAccount(
            id=account_id,
            tenant_id=seeded_tenant["tenant_id"],
            waba_id="waba_p3",
            phone_number_id=phone_number_id,
            business_access_token="tok_p3",
            credit_line_attached=False,
            status=READY,
            lifecycle_version=1,
        )
        session.add(account)
        bootstrap_ready(account, correlation_id="req_seed_p3")
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


def _inbound_job(
    *,
    tenant_id: str,
    phone_number_id: str,
    messages: list[dict[str, Any]],
    correlation_id: str = "req_p3_inbound",
) -> dict[str, Any]:
    return {
        "job_type": "inbound_webhook",
        "event": {
            "event_id": new_id("evt"),
            "event_type": "webhook.inbound.received.v1",
            "occurred_at": "2026-08-02T12:00:00Z",
            "tenant_id": tenant_id,
            "correlation_id": correlation_id,
            "data": {
                "provider": "meta_whatsapp",
                "channel": "whatsapp",
                "received_at": "2026-08-02T12:00:00Z",
                "payload_ref": "wh_p3",
                "kind": "inbound_message",
            },
        },
        "payload": {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "waba",
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "metadata": {"phone_number_id": phone_number_id},
                                "messages": messages,
                            },
                        }
                    ],
                }
            ],
        },
    }


def test_inbound_persist_and_duplicate_idempotent(
    seeded_whatsapp: dict[str, str],
    redis_client,
) -> None:
    settings = get_settings()
    tenant_id = seeded_whatsapp["tenant_id"]
    job = _inbound_job(
        tenant_id=tenant_id,
        phone_number_id=seeded_whatsapp["phone_number_id"],
        messages=[
            {
                "id": "wamid.P3_A",
                "from": "385911000100",
                "type": "text",
                "text": {"body": "hello"},
            }
        ],
        correlation_id="req_p3_dup",
    )
    process_inbound_job(job)
    process_inbound_job(job)

    with session_scope() as session:
        rows = session.scalars(
            select(Message).where(
                Message.tenant_id == tenant_id,
                Message.provider_message_id == "wamid.P3_A",
            )
        ).all()
        assert len(rows) == 1
        assert rows[0].direction == "inbound"
        assert rows[0].status == "received"
        assert rows[0].correlation_id == "req_p3_dup"
        assert rows[0].payload.get("text", {}).get("body") == "hello"
        message_id = rows[0].id
        assert session.scalar(select(func.count()).select_from(Conversation)) == 1

    events = [
        json.loads(raw)
        for raw in redis_client.lrange(settings.delivery_events_key, 0, -1)
        if json.loads(raw).get("event_type") == "message.inbound.received.v1"
    ]
    assert len(events) == 1
    assert events[0]["correlation_id"] == "req_p3_dup"
    assert events[0]["data"]["message_id"] == message_id
    assert events[0]["data"]["provider_message_id"] == "wamid.P3_A"


def test_thread_api_oldest_to_newest(
    seeded_whatsapp: dict[str, str],
    redis_client,
) -> None:
    del redis_client
    from omnimsg_api.main import app

    tenant_id = seeded_whatsapp["tenant_id"]
    phone_number_id = seeded_whatsapp["phone_number_id"]
    contact = "385911000200"
    for mid, body in [
        ("wamid.P3_ORD_A", "A"),
        ("wamid.P3_ORD_B", "B"),
        ("wamid.P3_ORD_C", "C"),
    ]:
        process_inbound_job(
            _inbound_job(
                tenant_id=tenant_id,
                phone_number_id=phone_number_id,
                messages=[
                    {
                        "id": mid,
                        "from": contact,
                        "type": "text",
                        "text": {"body": body},
                    }
                ],
                correlation_id=f"req_{mid}",
            )
        )

    with session_scope() as session:
        conversation_id = session.scalars(
            select(Conversation.id).where(
                Conversation.tenant_id == tenant_id,
                Conversation.contact_external_id == contact,
            )
        ).one()

    client = TestClient(app)
    response = client.get(
        f"/v1/conversations/{conversation_id}/messages",
        headers={
            "X-Tenant-Id": seeded_whatsapp["tenant_id"],
            "X-Api-Key-Id": seeded_whatsapp["api_key_id"],
            "X-Correlation-Id": "req_thread_list",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"] == conversation_id
    texts = [
        (m.get("provider_message_id"), m["direction"]) for m in body["messages"]
    ]
    assert [t[0] for t in texts] == [
        "wamid.P3_ORD_A",
        "wamid.P3_ORD_B",
        "wamid.P3_ORD_C",
    ]
    assert all(t[1] == "inbound" for t in texts)
