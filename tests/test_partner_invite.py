"""Partner invite bootstrap (capability-partner-onboarding-v1)."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from omnimsg_api.admin import mount_admin
from omnimsg_api.partner_invite import mount_partner_invite_routes
from omnimsg_common.db.models import AdminAuditEvent, ApiKey, PartnerInvite, Tenant
from omnimsg_common.db.session import session_scope
from omnimsg_common.settings import get_settings
from sqlalchemy import func, select

CONTRACT = Path(__file__).resolve().parents[1] / "packages/contracts/openapi/openapi.yaml"


def _basic(user: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.fixture
def invite_app(monkeypatch: pytest.MonkeyPatch, postgres_ready: bool) -> FastAPI:
    del postgres_ready
    monkeypatch.setenv("ADMIN_USERNAME", "ops")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret-ops")
    monkeypatch.setenv("ADMIN_READ_ONLY", "false")
    monkeypatch.setenv("PORTAL_BASE_URL", "https://app.omnimsg.io")
    monkeypatch.setenv("OPENAPI_CONTRACT_PATH", str(CONTRACT))
    get_settings.cache_clear()
    app = FastAPI()
    mount_partner_invite_routes(app)
    assert mount_admin(app) is not None
    return app


def test_create_accept_bootstraps_tenant_and_key(
    invite_app: FastAPI, db_clean: None
) -> None:
    del db_clean
    client = TestClient(invite_app)
    created = client.post(
        "/admin/partner-invites",
        headers=_basic("ops", "secret-ops"),
        json={"partner_name": "Acme Partner", "partner_email": "ops@acme.example"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "pending"
    assert body["onboard_url"].startswith("https://app.omnimsg.io/onboard/")
    token = body["token"]
    invite_id = body["id"]

    accepted = client.post("/v1/partner-invites/accept", json={"token": token})
    assert accepted.status_code == 200, accepted.text
    payload = accepted.json()
    assert payload["invite_id"] == invite_id
    assert payload["api_key"].startswith("omni_")
    tenant_id = payload["tenant_id"]
    api_key_id = payload["api_key_id"]

    with session_scope() as session:
        tenant = session.get(Tenant, tenant_id)
        assert tenant is not None
        assert tenant.name == "Acme Partner"
        assert tenant.status == "active"
        key = session.get(ApiKey, api_key_id)
        assert key is not None
        assert key.tenant_id == tenant_id
        invite = session.get(PartnerInvite, invite_id)
        assert invite is not None
        assert invite.status == "accepted"
        actions = {
            row.action
            for row in session.scalars(
                select(AdminAuditEvent).where(
                    AdminAuditEvent.correlation_id.is_not(None)
                )
            )
        }
        assert "invite_created" in actions
        assert "invite_accepted" in actions
        assert "tenant_created" in actions
        assert "apikey_created" in actions


def test_reaccept_returns_410_without_second_tenant(
    invite_app: FastAPI, db_clean: None
) -> None:
    del db_clean
    client = TestClient(invite_app)
    created = client.post(
        "/admin/partner-invites",
        headers=_basic("ops", "secret-ops"),
        json={"partner_name": "Once Partner"},
    )
    token = created.json()["token"]
    first = client.post("/v1/partner-invites/accept", json={"token": token})
    assert first.status_code == 200
    second = client.post("/v1/partner-invites/accept", json={"token": token})
    assert second.status_code == 410
    assert second.json()["error"]["code"] == "invite_already_accepted"
    assert second.json()["error"]["message"] == "Invite already accepted"

    with session_scope() as session:
        assert session.scalar(select(func.count()).select_from(Tenant)) == 1
        assert session.scalar(select(func.count()).select_from(ApiKey)) == 1


def test_revoke_then_accept_410(invite_app: FastAPI, db_clean: None) -> None:
    del db_clean
    client = TestClient(invite_app)
    created = client.post(
        "/admin/partner-invites",
        headers=_basic("ops", "secret-ops"),
        json={"partner_name": "Revoked Co"},
    )
    invite_id = created.json()["id"]
    token = created.json()["token"]
    revoked = client.post(
        f"/admin/partner-invites/{invite_id}/revoke",
        headers=_basic("ops", "secret-ops"),
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    accepted = client.post("/v1/partner-invites/accept", json={"token": token})
    assert accepted.status_code == 410
    assert accepted.json()["error"]["code"] == "invite_revoked"


def test_expired_invite_410(
    invite_app: FastAPI, db_clean: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    del db_clean
    monkeypatch.setenv("PARTNER_INVITE_TTL_HOURS", "1")
    get_settings.cache_clear()
    client = TestClient(invite_app)
    created = client.post(
        "/admin/partner-invites",
        headers=_basic("ops", "secret-ops"),
        json={"partner_name": "Expired Co", "ttl_hours": 1},
    )
    assert created.status_code == 201
    token = created.json()["token"]
    invite_id = created.json()["id"]

    from datetime import UTC, datetime, timedelta

    with session_scope() as session:
        row = session.get(PartnerInvite, invite_id)
        assert row is not None
        row.expires_at = datetime.now(UTC) - timedelta(minutes=1)

    accepted = client.post("/v1/partner-invites/accept", json={"token": token})
    assert accepted.status_code == 410
    assert accepted.json()["error"]["code"] == "invite_expired"


def test_create_requires_admin_auth(invite_app: FastAPI, db_clean: None) -> None:
    del db_clean
    client = TestClient(invite_app)
    response = client.post(
        "/admin/partner-invites",
        json={"partner_name": "No Auth"},
    )
    assert response.status_code == 401
