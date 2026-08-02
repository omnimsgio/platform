"""URL helpers for reverse-proxy / Traefik edges."""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse


def is_internal_service_host(host: str) -> bool:
    h = (host or "").lower()
    return "omnimsgio-api" in h or h.startswith("omnimsgio-")


def rewrite_internal_location(location: str, *, public_origin: str) -> str:
    """Rewrite Absolute Location pointing at internal API host to public origin."""
    if not location or not public_origin:
        return location
    parsed = urlparse(location)
    origin = urlparse(public_origin)
    if not parsed.netloc:
        return location
    if is_internal_service_host(parsed.netloc):
        return urlunparse(
            (
                origin.scheme or "https",
                origin.netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            )
        )
    return location
