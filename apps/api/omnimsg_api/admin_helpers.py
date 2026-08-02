"""Shared helpers for SQLAdmin views (ADR-0022)."""

from __future__ import annotations

from typing import Any

from omnimsg_common.ids import new_id
from omnimsg_common.proxy_urls import is_internal_service_host, rewrite_internal_location
from starlette.datastructures import URL
from starlette.requests import Request

from omnimsg_api import admin as admin_mod

__all__ = [
    "actor",
    "audit_meta",
    "client_ip",
    "public_url",
    "record_audit",
    "rewrite_internal_location",
]


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


def public_url(request: Request, name: str, **path_params: Any) -> str:
    """Build an absolute URL using forwarded host/proto behind Traefik/gateway.

    ``request.url_for`` alone often yields the internal Docker hostname
    (e.g. ``omnimsgio-api:8000``) when the admin is reverse-proxied.
    """
    generated = URL(str(request.url_for(name, **path_params)))
    proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip()
    host = (request.headers.get("x-forwarded-host") or "").split(",")[0].strip()
    if not host:
        raw_host = (request.headers.get("host") or "").split(",")[0].strip()
        if raw_host and not is_internal_service_host(raw_host):
            host = raw_host
    if proto and host:
        return str(generated.replace(scheme=proto, netloc=host))
    if host:
        return str(generated.replace(netloc=host))
    return str(generated)
