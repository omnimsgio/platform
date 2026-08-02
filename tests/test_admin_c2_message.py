"""Ops admin C2.4: Message SQLAdmin — strictly read-only observability."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from omnimsg_api.admin import mount_admin
from omnimsg_api.admin_message import mask_recipient, redact_payload
from omnimsg_common.db.models import Message
from omnimsg_common.db.session import session_scope
from omnimsg_common.ids import new_id
from omnimsg_common.settings import get_settings

CONTRACT = Path(__file__).resolve().parents[1] / "packages/contracts/openapi/openapi.yaml"


def _basic(user: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.fixture
def admin_app(monkeypatch: pytest.MonkeyPatch, postgres_ready: bool) -> FastAPI:
    del postgres_ready
    monkeypatch.setenv("ADMIN_USERNAME", "ops")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret-ops")
    monkeypatch.setenv("ADMIN_READ_ONLY", "false")
    monkeypatch.setenv("OPENAPI_CONTRACT_PATH", str(CONTRACT))
    get_settings.cache_clear()
    app = FastAPI()
    assert mount_admin(app) is not None
    return app


def test_mask_recipient_phone_and_email() -> None:
    assert mask_recipient("+385911234567").endswith("4567")
    assert "911234567" not in mask_recipient("+385911234567")
    assert "@example.com" in mask_recipient("ops@example.com")
    assert "ops@" not in mask_recipient("ops@example.com")


def test_redact_payload_tokens_and_phones() -> None:
    raw = {
        "to": "+385911234567",
        "access_token": "EAAGsupersecret",
        "text": {"body": "hello"},
        "nested": {"api_key": "omni_should_hide_this_value_xxxxx"},
    }
    out = redact_payload(raw)
    assert out["access_token"] == "[redacted]"
    assert out["nested"]["api_key"] == "[redacted]"
    assert "911234567" not in str(out["to"])
    assert out["text"]["body"] == "hello"


def test_message_list_and_detail_read_only(
    admin_app: FastAPI, seeded_tenant: dict[str, str]
) -> None:
    msg_id = new_id("msg")
    with session_scope() as session:
        session.add(
            Message(
                id=msg_id,
                tenant_id=seeded_tenant["tenant_id"],
                channel="whatsapp",
                direction="outbound",
                to="+385911234567",
                from_address=None,
                type="text",
                status="queued",
                correlation_id="req_c24_test",
                payload={
                    "text": {"body": "hi"},
                    "access_token": "EAAGleak",
                    "error": "provider timeout",
                    "provider_message_id": "wamid.TEST",
                },
            )
        )

    client = TestClient(admin_app)
    listing = client.get("/admin/message/list", headers=_basic("ops", "secret-ops"))
    assert listing.status_code == 200
    body = listing.text
    assert "Messages" in body
    assert msg_id in body or "req_c24_test" in body
    assert "+385911234567" not in body
    assert "EAAGleak" not in body
    # No mutation controls.
    assert "New Message" not in body
    assert b"action-delete" not in listing.content or "Delete selected" not in body

    details = client.get(
        f"/admin/message/details/{msg_id}",
        headers=_basic("ops", "secret-ops"),
    )
    assert details.status_code == 200
    assert "EAAGleak" not in details.text
    assert "[redacted]" in details.text
    assert "provider timeout" in details.text
    assert "+385911234567" not in details.text

    # Write endpoints must stay blocked by can_* and middleware for POST.
    create = client.get("/admin/message/create", headers=_basic("ops", "secret-ops"))
    assert create.status_code in {403, 404}


def test_message_source_is_strictly_read_only() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "apps/api/omnimsg_api/admin_message.py"
    ).read_text(encoding="utf-8")
    assert "can_create = False" in source
    assert "can_edit = False" in source
    assert "can_delete = False" in source
    assert "@action" not in source
    assert "session.commit" not in source
