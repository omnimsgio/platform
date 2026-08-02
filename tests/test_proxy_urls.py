"""Unit tests for proxy URL rewriting behind Traefik."""

from __future__ import annotations

from omnimsg_common.proxy_urls import rewrite_internal_location


def test_rewrite_internal_api_location() -> None:
    out = rewrite_internal_location(
        "http://omnimsgio-api:8000/admin/api-key/reveal",
        public_origin="https://api.omnimsg.io",
    )
    assert out == "https://api.omnimsg.io/admin/api-key/reveal"


def test_rewrite_leaves_public_location() -> None:
    loc = "https://api.omnimsg.io/admin/api-key/list"
    assert (
        rewrite_internal_location(loc, public_origin="https://api.omnimsg.io") == loc
    )
