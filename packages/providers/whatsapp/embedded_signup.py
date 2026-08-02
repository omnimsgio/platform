"""Meta Graph helpers for WhatsApp Embedded Signup (code exchange + WABA ops)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from whatsapp.meta import DEFAULT_API_VERSION, DEFAULT_GRAPH_BASE_URL

logger = logging.getLogger(__name__)


class MetaGraphError(Exception):
    """Raised when a Meta Graph call fails."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_code: str | None = None,
        error_subcode: str | None = None,
        fbtrace_id: str | None = None,
        body: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.error_subcode = error_subcode
        self.fbtrace_id = fbtrace_id
        self.body = body or {}


class MetaEmbeddedSignupClient:
    """OAuth code exchange, WABA subscribe, and token health checks."""

    def __init__(
        self,
        *,
        app_id: str,
        app_secret: str,
        api_version: str = DEFAULT_API_VERSION,
        base_url: str = DEFAULT_GRAPH_BASE_URL,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._app_id = str(app_id).strip() if app_id else ""
        self._app_secret = str(app_secret).strip() if app_secret else ""
        self._api_version = api_version.strip().lstrip("/") or DEFAULT_API_VERSION
        self._base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> MetaEmbeddedSignupClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def exchange_code(
        self,
        code: str,
        *,
        correlation_id: str,
    ) -> dict[str, Any]:
        """Exchange Embedded Signup auth code for a business access token."""
        if not self._app_id or not self._app_secret:
            raise ValueError("app_id and app_secret are required for code exchange")
        url = f"{self._base_url}/{self._api_version}/oauth/access_token"
        params = {
            "client_id": self._app_id,
            "client_secret": self._app_secret,
            "code": code.strip(),
        }
        logger.info(
            "meta es exchange_code correlation_id=%s",
            correlation_id,
        )
        response = self._client.get(url, params=params)
        return self._parse(response, correlation_id=correlation_id, op="exchange_code")

    def subscribe_app(
        self,
        *,
        waba_id: str,
        access_token: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        """Subscribe the app to a WABA for webhook delivery."""
        url = f"{self._base_url}/{self._api_version}/{waba_id.strip()}/subscribed_apps"
        logger.info(
            "meta es subscribe_app waba_id=%s correlation_id=%s",
            waba_id,
            correlation_id,
        )
        response = self._client.post(
            url,
            headers={"Authorization": f"Bearer {access_token.strip()}"},
        )
        return self._parse(response, correlation_id=correlation_id, op="subscribe_app")

    def get_subscribed_apps(
        self,
        *,
        waba_id: str,
        access_token: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        """List apps subscribed to a WABA (Graph confirmation of webhook subscription)."""
        url = f"{self._base_url}/{self._api_version}/{waba_id.strip()}/subscribed_apps"
        logger.info(
            "meta get_subscribed_apps waba_id=%s correlation_id=%s",
            waba_id,
            correlation_id,
        )
        response = self._client.get(
            url,
            headers={"Authorization": f"Bearer {access_token.strip()}"},
        )
        return self._parse(
            response,
            correlation_id=correlation_id,
            op="get_subscribed_apps",
        )

    def health_phone_numbers(
        self,
        *,
        waba_id: str,
        access_token: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        """Verify the business token can list WABA phone numbers."""
        url = f"{self._base_url}/{self._api_version}/{waba_id.strip()}/phone_numbers"
        logger.info(
            "meta es health_phone_numbers waba_id=%s correlation_id=%s",
            waba_id,
            correlation_id,
        )
        response = self._client.get(
            url,
            headers={"Authorization": f"Bearer {access_token.strip()}"},
        )
        return self._parse(
            response,
            correlation_id=correlation_id,
            op="health_phone_numbers",
        )

    def register_phone(
        self,
        *,
        phone_number_id: str,
        pin: str,
        access_token: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        """Register a Cloud API phone number (PIN / 2FA)."""
        url = (
            f"{self._base_url}/{self._api_version}/{phone_number_id.strip()}/register"
        )
        logger.info(
            "meta register_phone phone_number_id=%s correlation_id=%s",
            phone_number_id,
            correlation_id,
        )
        response = self._client.post(
            url,
            headers={"Authorization": f"Bearer {access_token.strip()}"},
            json={
                "messaging_product": "whatsapp",
                "pin": pin.strip(),
            },
        )
        return self._parse(response, correlation_id=correlation_id, op="register_phone")

    def _parse(
        self,
        response: httpx.Response,
        *,
        correlation_id: str,
        op: str,
    ) -> dict[str, Any]:
        try:
            body = response.json()
        except Exception:
            body = {"raw": response.text[:500]}
        if response.is_success and isinstance(body, dict):
            return body
        err = body.get("error") if isinstance(body, dict) else None
        message = "Meta Graph request failed"
        error_code = None
        error_subcode = None
        fbtrace_id = None
        if isinstance(err, dict):
            message = str(err.get("message") or message)
            if err.get("code") is not None:
                error_code = str(err.get("code"))
            if err.get("error_subcode") is not None:
                error_subcode = str(err.get("error_subcode"))
            if err.get("fbtrace_id") is not None:
                fbtrace_id = str(err.get("fbtrace_id"))
        logger.warning(
            "meta %s failed status=%s correlation_id=%s code=%s subcode=%s "
            "fbtrace_id=%s message=%s",
            op,
            response.status_code,
            correlation_id,
            error_code,
            error_subcode,
            fbtrace_id,
            message,
        )
        raise MetaGraphError(
            message,
            status_code=response.status_code,
            error_code=error_code,
            error_subcode=error_subcode,
            fbtrace_id=fbtrace_id,
            body=body if isinstance(body, dict) else {"body": body},
        )
