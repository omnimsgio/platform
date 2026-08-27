"""Tests for App Review BM token runner (gateway module, isolated app)."""

from __future__ import annotations

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from omnimsg_gateway.app_review_bm_runner import mount_app_review_bm_runner


def _app(monkeypatch, **env: str) -> FastAPI:
    monkeypatch.setenv("FEATURE_APP_REVIEW_BM_RUNNER", "true")
    monkeypatch.setenv("FEATURE_APP_REVIEW_BM_DEMO", "true")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    from omnimsg_common.settings import get_settings

    get_settings.cache_clear()
    app = FastAPI()
    mount_app_review_bm_runner(app)
    return app


def _mock_graph(monkeypatch) -> list[str]:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        auth = request.headers.get("Authorization", "")
        assert auth.startswith("Bearer ")
        assert "EAA" not in str(request.url)
        if "owned_whatsapp" in str(request.url):
            return httpx.Response(
                200, json={"data": [{"id": "1", "name": "Test WABA"}]}
            )
        if "businesses" in str(request.url):
            return httpx.Response(200, json={"data": []})
        return httpx.Response(200, json={"id": "1329905112443890", "name": "Finestar"})

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(
        "omnimsg_gateway.app_review_bm_runner.httpx.AsyncClient", factory
    )
    return calls


def test_bm_runner_page_enabled(monkeypatch) -> None:
    client = TestClient(_app(monkeypatch))
    response = client.get("/app-review/bm-runner")
    assert response.status_code == 200
    assert "business_management runner" in response.text
    assert "Access token" in response.text


def test_bm_probe_runs_three_calls(monkeypatch) -> None:
    calls = _mock_graph(monkeypatch)
    client = TestClient(_app(monkeypatch))
    response = client.post(
        "/app-review/bm-probe",
        json={
            "access_token": "EAA" + ("x" * 40),
            "business_id": "1329905112443890",
            "graph_version": "v21.0",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["calls"]) == 3
    assert all(c["http_status"] == 200 for c in body["calls"])
    assert len(calls) == 3


def test_bm_discover_uses_system_user_token(monkeypatch) -> None:
    calls = _mock_graph(monkeypatch)
    client = TestClient(
        _app(
            monkeypatch,
            META_BUSINESS_ACCESS_TOKEN="EAA" + ("s" * 40),
            META_BUSINESS_ID="1329905112443890",
        )
    )
    response = client.post(
        "/app-review/bm-discover",
        json={"business_id": "1329905112443890"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["auth_mode"] == "system_user"
    assert body["system_user"] == "omnimsg_api"
    assert body["business_id"] == "1329905112443890"
    assert len(body["calls"]) == 3
    assert body["calls"][0]["label"] == "A"
    assert body["calls"][0]["role"] == "informative"
    assert body["calls"][1]["label"] == "B"
    assert body["calls"][2]["label"] == "C"
    assert all(c["http_status"] == 200 for c in body["calls"])
    assert "access_token" not in response.text.lower()
    assert "EAAs" not in response.text
    assert len(calls) == 3


def test_bm_discover_requires_server_token(monkeypatch) -> None:
    client = TestClient(_app(monkeypatch, META_BUSINESS_ACCESS_TOKEN=""))
    response = client.post("/app-review/bm-discover", json={})
    assert response.status_code == 503
    assert response.json()["error"] == "misconfigured"


def test_bm_discover_disabled(monkeypatch) -> None:
    client = TestClient(
        _app(
            monkeypatch,
            FEATURE_APP_REVIEW_BM_DEMO="false",
            META_BUSINESS_ACCESS_TOKEN="EAA" + ("s" * 40),
        )
    )
    response = client.post("/app-review/bm-discover", json={})
    assert response.status_code == 404
