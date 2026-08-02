"""Shared helpers for SQLAdmin views (ADR-0022)."""

from __future__ import annotations

from typing import Any

from omnimsg_common.ids import new_id
from starlette.requests import Request

from omnimsg_api import admin as admin_mod


def actor(request: Request) -> str:
    user = request.session.get("admin_user")
    return user if isinstance(user, str) and user else "unknown"


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def audit_meta(request: Request) -> dict[str, str | None]:
    cid = request.headers.get("x-correlation-id") or new_id("req")
    return {
        "correlation_id": cid,
        "request_id": cid,
        "request_ip": client_ip(request),
        "user_agent": request.headers.get("user-agent"),
    }


def record_audit(**kwargs: Any) -> None:
    admin_mod.record_admin_audit(**kwargs)
