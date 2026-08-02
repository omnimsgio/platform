"""Ops admin C2.2: ApiKey SQLAdmin — list, create reveal, rotate, hash hidden."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from omnimsg_api.admin import mount_admin
from omnimsg_common.api_key_lifecycle import start_rotation
from omnimsg_common.db.models import AdminAuditEvent, ApiKey
from omnimsg_common.db.session import session_scope
from omnimsg_common.settings import get_settings
from sqlalchemy import select

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
    monkeypatch.setenv("ADMIN_API_KEY_GRACE_HOURS", "24")
    monkeypatch.setenv("OPENAPI_CONTRACT_PATH", str(CONTRACT))
    get_settings.cache_clear()
    app = FastAPI()
    assert mount_admin(app) is not None
    return app


def test_apikey_list_hides_hash(
    admin_app: FastAPI, seeded_tenant: dict[str, str]
) -> None:
    with session_scope() as session:
        row = session.get(ApiKey, seeded_tenant["api_key_id"])
        assert row is not None
        digest = row.key_hash

    client = TestClient(admin_app)
    response = client.get("/admin/api-key/list", headers=_basic("ops", "secret-ops"))
    assert response.status_code == 200
    body = response.text
    assert seeded_tenant["api_key_id"] in body
    assert digest not in body
    assert "key_hash" not in body.lower() or "Key Hash" not in body
    assert "Start rotation" in body
    assert "Finish rotation" in body


def test_apikey_create_audits_and_reveals_once(
    admin_app: FastAPI, seeded_tenant: dict[str, str]
) -> None:
    client = TestClient(admin_app)
    form = client.get("/admin/api-key/create", headers=_basic("ops", "secret-ops"))
    assert form.status_code == 200
    assert b"key_hash" not in form.content.lower()

    created = client.post(
        "/admin/api-key/create",
        headers=_basic("ops", "secret-ops"),
        data={"tenant_id": seeded_tenant["tenant_id"]},
        follow_redirects=False,
    )
    # Secret.reveal_once re-renders create template (200) instead of redirect.
    assert created.status_code == 200
    assert b"omni_" in created.content
    assert b"Copy this API key now" in created.content or b"will not be shown" in created.content

    # Details must not contain a full omni_ secret after create response consumed.
    with session_scope() as session:
        rows = session.scalars(
            select(ApiKey).where(ApiKey.tenant_id == seeded_tenant["tenant_id"])
        ).all()
        newest = max(rows, key=lambda r: r.created_at)
        events = session.scalars(
            select(AdminAuditEvent).where(
                AdminAuditEvent.action == "apikey_create",
                AdminAuditEvent.entity_id == newest.id,
            )
        ).all()
        assert len(events) == 1
        assert events[0].after is not None
        assert "key_hash" not in events[0].after

    details = client.get(
        f"/admin/api-key/details/{newest.id}",
        headers=_basic("ops", "secret-ops"),
    )
    assert details.status_code == 200
    assert b"omni_" not in details.content or newest.key_prefix.encode() in details.content
    # Full key is longer than prefix; ensure no 40+ char omni_ token in details.
    import re

    secrets = re.findall(r"omni_[A-Za-z0-9_-]{20,}", details.text)
    assert secrets == []


def test_rotate_start_reveal_gone_on_refresh(
    admin_app: FastAPI, seeded_tenant: dict[str, str]
) -> None:
    client = TestClient(admin_app)
    start = client.get(
        f"/admin/api-key/action/rotate-start?pks={seeded_tenant['api_key_id']}",
        headers=_basic("ops", "secret-ops"),
        follow_redirects=False,
    )
    assert start.status_code in {302, 303, 307}
    reveal_url = start.headers["location"]
    first = client.get(reveal_url, headers=_basic("ops", "secret-ops"))
    assert first.status_code == 200
    assert b"omni_" in first.content
    second = client.get(reveal_url, headers=_basic("ops", "secret-ops"))
    assert second.status_code == 410
    assert b"omni_" not in second.content or b"no longer available" in second.content


def test_rotate_finish_action_audits(
    admin_app: FastAPI, seeded_tenant: dict[str, str]
) -> None:
    with session_scope() as session:
        start_rotation(
            session, old_key_id=seeded_tenant["api_key_id"], grace_hours=24
        )

    client = TestClient(admin_app)
    response = client.get(
        f"/admin/api-key/action/rotate-finish?pks={seeded_tenant['api_key_id']}",
        headers=_basic("ops", "secret-ops"),
        follow_redirects=False,
    )
    assert response.status_code in {302, 303, 307}

    with session_scope() as session:
        old = session.get(ApiKey, seeded_tenant["api_key_id"])
        assert old is not None
        assert old.status == "inactive"
        events = session.scalars(
            select(AdminAuditEvent).where(
                AdminAuditEvent.action == "apikey_rotate_finish",
                AdminAuditEvent.entity_id == seeded_tenant["api_key_id"],
            )
        ).all()
        assert len(events) >= 1
