"""Ops admin C2.1: Tenant SQLAdmin view + deactivate audit."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from omnimsg_api.admin import mount_admin
from omnimsg_common.db.models import AdminAuditEvent, Tenant
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
    monkeypatch.setenv("OPENAPI_CONTRACT_PATH", str(CONTRACT))
    get_settings.cache_clear()
    app = FastAPI()
    assert mount_admin(app) is not None
    return app


@pytest.fixture
def admin_readonly_app(monkeypatch: pytest.MonkeyPatch, postgres_ready: bool) -> FastAPI:
    del postgres_ready
    monkeypatch.setenv("ADMIN_USERNAME", "ops")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret-ops")
    monkeypatch.setenv("ADMIN_READ_ONLY", "true")
    monkeypatch.setenv("OPENAPI_CONTRACT_PATH", str(CONTRACT))
    get_settings.cache_clear()
    app = FastAPI()
    assert mount_admin(app) is not None
    return app


def test_tenant_list_visible(admin_app: FastAPI, seeded_tenant: dict[str, str]) -> None:
    del seeded_tenant
    client = TestClient(admin_app)
    response = client.get("/admin/tenant/list", headers=_basic("ops", "secret-ops"))
    assert response.status_code == 200
    assert b"Test Tenant" in response.content
    assert b"ten_test" in response.content


def test_tenant_deactivate_writes_audit(
    admin_app: FastAPI, seeded_tenant: dict[str, str]
) -> None:
    tenant_id = seeded_tenant["tenant_id"]
    client = TestClient(admin_app)
    response = client.get(
        f"/admin/tenant/action/deactivate?pks={tenant_id}",
        headers=_basic("ops", "secret-ops"),
        follow_redirects=False,
    )
    assert response.status_code in {302, 303, 307}

    with session_scope() as session:
        row = session.get(Tenant, tenant_id)
        assert row is not None
        assert row.status == "inactive"
        events = session.scalars(
            select(AdminAuditEvent).where(
                AdminAuditEvent.action == "tenant_deactivate",
                AdminAuditEvent.entity_id == tenant_id,
            )
        ).all()
        assert len(events) == 1
        assert events[0].actor == "ops"
        assert events[0].entity_type == "Tenant"
        assert events[0].before == {"id": tenant_id, "status": "active"}
        assert events[0].after == {"id": tenant_id, "status": "inactive"}


def test_tenant_action_blocked_when_read_only(
    admin_readonly_app: FastAPI, seeded_tenant: dict[str, str]
) -> None:
    tenant_id = seeded_tenant["tenant_id"]
    client = TestClient(admin_readonly_app)
    response = client.get(
        f"/admin/tenant/action/deactivate?pks={tenant_id}",
        headers=_basic("ops", "secret-ops"),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "admin_read_only"

    with session_scope() as session:
        row = session.get(Tenant, tenant_id)
        assert row is not None
        assert row.status == "active"


def test_tenant_create_audits(admin_app: FastAPI, db_clean: None) -> None:
    del db_clean
    client = TestClient(admin_app)
    # Hit create form first (session + CSRF cookies as SQLAdmin expects).
    form = client.get("/admin/tenant/create", headers=_basic("ops", "secret-ops"))
    assert form.status_code == 200

    response = client.post(
        "/admin/tenant/create",
        headers=_basic("ops", "secret-ops"),
        data={"id": "ten_c2_created", "name": "C2 Tenant", "status": "active"},
        follow_redirects=False,
    )
    # SQLAdmin may redirect on success or re-render; accept either with DB truth.
    assert response.status_code in {200, 302, 303}

    with session_scope() as session:
        row = session.get(Tenant, "ten_c2_created")
        assert row is not None
        assert row.name == "C2 Tenant"
        assert row.status == "active"
        events = session.scalars(
            select(AdminAuditEvent).where(
                AdminAuditEvent.action == "tenant_create",
                AdminAuditEvent.entity_id == "ten_c2_created",
            )
        ).all()
        assert len(events) == 1
