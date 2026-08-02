"""Ops admin C2.3: WhatsApp account read-mostly + transition-only mutations."""

from __future__ import annotations

import ast
import base64
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from omnimsg_api.admin import mount_admin
from omnimsg_common.db.models import AdminAuditEvent, TenantWhatsappAccount
from omnimsg_common.db.session import session_scope
from omnimsg_common.ids import new_id
from omnimsg_common.settings import get_settings
from omnimsg_common.whatsapp_lifecycle import (
    ERROR,
    READY,
    REASON_HEALTH_CHECK_FAILED,
    REASON_HEALTH_OK,
    HEALTH_CHECK_PENDING,
    bootstrap_ready,
    transition,
)
from sqlalchemy import select

CONTRACT = Path(__file__).resolve().parents[1] / "packages/contracts/openapi/openapi.yaml"
ADMIN_WA = (
    Path(__file__).resolve().parents[1]
    / "apps/api/omnimsg_api/admin_whatsapp.py"
)


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


def test_admin_whatsapp_source_never_assigns_status_directly() -> None:
    """Architecture rule: SQLAdmin must not write TenantWhatsappAccount.status."""
    source = ADMIN_WA.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Attribute) and target.attr == "status":
                # Allow reading comparisons only — Assign to .status is forbidden.
                forbidden.append(f"line {node.lineno}: status assignment")
            if (
                isinstance(target, ast.Attribute)
                and target.attr == "status"
                and isinstance(target.value, ast.Name)
            ):
                forbidden.append(f"line {node.lineno}: {target.value.id}.status =")
    assert "transition(" in source
    assert "RetryService" in source
    assert not forbidden, forbidden
    # Token / identity fields must not be in editable forms.
    assert "can_edit = False" in source
    assert "can_create = False" in source


def test_whatsapp_list_masks_token(
    admin_app: FastAPI, seeded_tenant: dict[str, str]
) -> None:
    secret = "EAAG_super_secret_token_value_do_not_leak"
    account_id = new_id("twa")
    with session_scope() as session:
        row = TenantWhatsappAccount(
            id=account_id,
            tenant_id=seeded_tenant["tenant_id"],
            waba_id="waba_1",
            phone_number_id="pn_1",
            business_access_token=secret,
            status=READY,
        )
        bootstrap_ready(row, correlation_id="req_seed")
        session.add(row)

    client = TestClient(admin_app)
    response = client.get(
        "/admin/tenant-whatsapp-account/list",
        headers=_basic("ops", "secret-ops"),
    )
    assert response.status_code == 200
    body = response.text
    assert account_id in body
    assert secret not in body
    assert "business_access_token" not in body or secret not in body

    details = client.get(
        f"/admin/tenant-whatsapp-account/details/{account_id}",
        headers=_basic("ops", "secret-ops"),
    )
    assert details.status_code == 200
    assert secret not in details.text
    assert "••••" in details.text


def test_mark_disconnected_uses_transition_and_audits(
    admin_app: FastAPI, seeded_tenant: dict[str, str]
) -> None:
    account_id = new_id("twa")
    with session_scope() as session:
        row = TenantWhatsappAccount(
            id=account_id,
            tenant_id=seeded_tenant["tenant_id"],
            waba_id="waba_d",
            phone_number_id="pn_d",
            business_access_token="token_d",
            status=READY,
        )
        bootstrap_ready(row, correlation_id="req_seed_d")
        session.add(row)

    client = TestClient(admin_app)
    response = client.get(
        f"/admin/tenant-whatsapp-account/action/mark-disconnected?pks={account_id}",
        headers=_basic("ops", "secret-ops"),
        follow_redirects=False,
    )
    assert response.status_code in {302, 303, 307}

    with session_scope() as session:
        row = session.get(TenantWhatsappAccount, account_id)
        assert row is not None
        assert row.status == "DISCONNECTED"
        events = session.scalars(
            select(AdminAuditEvent).where(
                AdminAuditEvent.action == "whatsapp_mark_disconnected",
                AdminAuditEvent.entity_id == account_id,
            )
        ).all()
        assert len(events) == 1
        assert events[0].after is not None
        assert "business_access_token" not in events[0].after
        assert events[0].after["status"] == "DISCONNECTED"


def test_retry_action_from_error(
    admin_app: FastAPI, seeded_tenant: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    account_id = new_id("twa")
    with session_scope() as session:
        row = TenantWhatsappAccount(
            id=account_id,
            tenant_id=seeded_tenant["tenant_id"],
            waba_id="waba_r",
            phone_number_id="pn_r",
            business_access_token="token_r",
            status=HEALTH_CHECK_PENDING,
        )
        transition(
            row,
            ERROR,
            status_reason=REASON_HEALTH_CHECK_FAILED,
            correlation_id="req_err",
            recovery_target=HEALTH_CHECK_PENDING,
            last_error="health failed",
        )
        session.add(row)

    # Avoid live Meta: stub health promote used by RetryService for HEALTH_CHECK_PENDING.
    from omnimsg_api.whatsapp_health import HealthCheckResult

    def _fake_check_and_promote(self, **kwargs):  # type: ignore[no-untyped-def]
        corr = kwargs.get("correlation_id") or "req_ok"
        with session_scope() as session:
            row = session.get(TenantWhatsappAccount, account_id)
            assert row is not None
            # RetryService already transitioned ERROR → HEALTH_CHECK_PENDING.
            if row.status == HEALTH_CHECK_PENDING:
                transition(
                    row,
                    READY,
                    status_reason=REASON_HEALTH_OK,
                    correlation_id=corr,
                )
                session.add(row)
                session.commit()
            return HealthCheckResult(
                status=READY,
                correlation_id=corr,
                already_healthy=False,
                account_id=account_id,
                waba_id="waba_r",
                phone_number_id="pn_r",
                status_reason=REASON_HEALTH_OK,
                badge="success",
                message="ok",
                checks={"graph": True},
            )

    monkeypatch.setattr(
        "omnimsg_api.whatsapp_health.HealthService.check_and_promote",
        _fake_check_and_promote,
    )

    client = TestClient(admin_app)
    response = client.get(
        f"/admin/tenant-whatsapp-account/action/retry-provisioning?pks={account_id}",
        headers=_basic("ops", "secret-ops"),
        follow_redirects=False,
    )
    assert response.status_code in {302, 303, 307}

    with session_scope() as session:
        row = session.get(TenantWhatsappAccount, account_id)
        assert row is not None
        assert row.status == READY
        events = session.scalars(
            select(AdminAuditEvent).where(
                AdminAuditEvent.action == "whatsapp_retry",
                AdminAuditEvent.entity_id == account_id,
            )
        ).all()
        assert len(events) == 1
