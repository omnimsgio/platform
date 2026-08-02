"""Gateway public docs / discovery surface (ADR-0021)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from omnimsg_common.openapi_contract import OpenAPIContractError, load_openapi_contract
from omnimsg_common.settings import get_settings

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT = REPO_ROOT / "packages" / "contracts" / "openapi" / "openapi.yaml"


@pytest.fixture
def gateway_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("OPENAPI_CONTRACT_PATH", str(CONTRACT))
    get_settings.cache_clear()
    from omnimsg_gateway.main import app

    with TestClient(app) as client:
        yield client


def test_load_contract_requires_x_contract_version() -> None:
    loaded = load_openapi_contract(CONTRACT)
    assert loaded.contract_version == "1.0.0"
    assert loaded.json_bytes.startswith(b"{")
    assert loaded.etag.startswith('"')


def test_discovery_and_version(gateway_client: TestClient) -> None:
    discovery = gateway_client.get("/")
    assert discovery.status_code == 200
    body = discovery.json()
    assert body["status"] == "ok"
    assert body["name"] == "OmniMsg API"
    assert body["docs"] == "/docs"
    assert body["openapi"] == "/openapi.json"
    assert body["health"] == "/health"
    assert body["contract_version"] == "1.0.0"
    assert "X-Content-Type-Options" in discovery.headers

    version = gateway_client.get("/version")
    assert version.status_code == 200
    vbody = version.json()
    assert "git_sha" in vbody
    assert "build_date" in vbody
    assert vbody["contract_version"] == "1.0.0"


def test_openapi_json_etag_and_304(gateway_client: TestClient) -> None:
    first = gateway_client.get("/openapi.json")
    assert first.status_code == 200
    assert first.headers.get("cache-control") == "public, max-age=300"
    etag = first.headers.get("etag")
    assert etag
    doc = first.json()
    assert doc["openapi"].startswith("3.")
    assert "/v1/messages" in doc["paths"]
    assert "info" in doc and doc["info"].get("x-contract-version") == "1.0.0"

    second = gateway_client.get("/openapi.json", headers={"If-None-Match": etag})
    assert second.status_code == 304


def test_docs_and_redoc(gateway_client: TestClient) -> None:
    docs = gateway_client.get("/docs")
    assert docs.status_code == 200
    assert "swagger" in docs.text.lower()
    assert docs.headers.get("content-security-policy")

    redoc = gateway_client.get("/redoc")
    assert redoc.status_code == 200
    assert "redoc" in redoc.text.lower()


def test_v1_health_public_no_bearer(gateway_client: TestClient) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "status": "ok",
                "version": "0.1.0",
                "checks": {
                    "database": True,
                    "redis": True,
                    "worker": None,
                    "provider": None,
                },
            },
        )
    )
    mock_client = httpx.AsyncClient(transport=transport, base_url="http://api.test")
    gateway_client.app.state.http = mock_client  # type: ignore[attr-defined]
    response = gateway_client.get("/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["checks"]["database"] is True


def test_v1_messages_still_requires_bearer(gateway_client: TestClient) -> None:
    response = gateway_client.post("/v1/messages", json={})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert "correlation_id" in response.json()["error"]


def test_fail_fast_missing_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    missing = tmp_path / "missing.yaml"
    monkeypatch.setenv("OPENAPI_CONTRACT_PATH", str(missing))
    get_settings.cache_clear()
    with pytest.raises(OpenAPIContractError):
        load_openapi_contract(missing)

    # Re-import path resolution must honor explicit missing env (no fallback).
    from omnimsg_common.openapi_contract import resolve_contract_path

    with pytest.raises(OpenAPIContractError):
        resolve_contract_path()

    # Fresh app import is heavy; assert lifespan loader fails the same way.
    from omnimsg_gateway.main import load_openapi_contract as gw_load
    from omnimsg_gateway.main import resolve_contract_path as gw_resolve

    with pytest.raises(OpenAPIContractError):
        gw_load(gw_resolve())
