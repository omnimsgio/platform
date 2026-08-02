"""Ops admin C1: Basic gate + ADMIN_READ_ONLY server-side deny."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from omnimsg_api.admin import mount_admin
from omnimsg_common.settings import get_settings

CONTRACT = Path(__file__).resolve().parents[1] / "packages/contracts/openapi/openapi.yaml"


def _basic(user: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.fixture
def admin_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setenv("ADMIN_USERNAME", "ops")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret-ops")
    monkeypatch.setenv("ADMIN_READ_ONLY", "false")
    get_settings.cache_clear()
    app = FastAPI()
    assert mount_admin(app) is not None
    return app


@pytest.fixture
def admin_readonly_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setenv("ADMIN_USERNAME", "ops")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret-ops")
    monkeypatch.setenv("ADMIN_READ_ONLY", "true")
    get_settings.cache_clear()
    app = FastAPI()
    assert mount_admin(app) is not None
    return app


def test_admin_home_with_basic(admin_app: FastAPI) -> None:
    client = TestClient(admin_app)
    response = client.get("/admin/home", headers=_basic("ops", "secret-ops"))
    assert response.status_code == 200
    assert b"OmniMsg Ops" in response.content
    assert b"Contract version" in response.content


def test_admin_write_denied_when_read_only(admin_readonly_app: FastAPI) -> None:
    client = TestClient(admin_readonly_app)
    response = client.post(
        "/admin/anything/create",
        headers=_basic("ops", "secret-ops"),
        data={"actor": "x"},
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "admin_read_only"


def test_gateway_admin_requires_basic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_USERNAME", "ops")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret-ops")
    monkeypatch.setenv("OPENAPI_CONTRACT_PATH", str(CONTRACT))
    get_settings.cache_clear()
    from omnimsg_gateway.main import app as gateway_app

    with TestClient(gateway_app) as client:
        denied = client.get("/admin/")
        assert denied.status_code == 401
        assert "www-authenticate" in {k.lower() for k in denied.headers.keys()}
