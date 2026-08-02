"""SQLAdmin ApiKey view (C2.2) — create once, two-step rotate, deactivate."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from omnimsg_common.api_key_lifecycle import (
    ApiKeyLifecycleError,
    deactivate_api_key,
    finish_rotation,
    key_public_snapshot,
    require_active_tenant,
    start_rotation,
)
from omnimsg_common.auth import generate_api_key, hash_api_key, key_display_prefix
from omnimsg_common.db.models import ApiKey
from omnimsg_common.db.session import get_session_factory
from omnimsg_common.ids import new_id
from omnimsg_common.settings import get_settings
from sqladmin import ModelView, action, expose
from sqladmin.secret import Secret
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from omnimsg_api.admin_helpers import actor, audit_meta, record_audit

_REVEAL_SESSION_KEY = "_api_key_reveal_once"


class ApiKeyAdmin(ModelView, model=ApiKey):
    name = "API Key"
    name_plural = "API Keys"
    icon = "fa-solid fa-key"
    column_list = [
        ApiKey.id,
        ApiKey.tenant_id,
        ApiKey.key_prefix,
        ApiKey.status,
        ApiKey.replaced_by_key_id,
        ApiKey.grace_expires_at,
        ApiKey.created_at,
    ]
    column_details_list = [
        ApiKey.id,
        ApiKey.tenant_id,
        ApiKey.key_prefix,
        ApiKey.status,
        ApiKey.replaced_by_key_id,
        ApiKey.replaces_key_id,
        ApiKey.grace_expires_at,
        ApiKey.created_at,
    ]
    column_searchable_list = [
        ApiKey.id,
        ApiKey.tenant_id,
        ApiKey.key_prefix,
        ApiKey.status,
    ]
    column_sortable_list = [ApiKey.created_at, ApiKey.status, ApiKey.tenant_id]
    form_columns = [ApiKey.tenant_id]
    # sqladmin skips FK columns unless form_include_pk is True.
    form_include_pk = True
    can_edit = False
    can_delete = False
    page_size = 50
    form_args = {
        "tenant_id": {"description": "Existing tenant id (e.g. ten_…)"},
    }

    def is_accessible(self, request: Request) -> bool:
        return bool(request.session.get("admin_user"))

    def is_visible(self, request: Request) -> bool:
        return self.is_accessible(request)

    async def check_can_create(self, request: Request) -> bool:
        return not get_settings().admin_read_only

    async def on_model_change(
        self,
        data: dict[str, Any],
        model: Any,
        is_created: bool,
        request: Request,
    ) -> None:
        if not is_created:
            return
        tenant_id = str(data.get("tenant_id") or "").strip()
        factory = get_session_factory()
        with factory() as session:
            require_active_tenant(session, tenant_id)
        raw = generate_api_key()
        # Drop any client-supplied secret material; generate server-side only.
        data.clear()
        data["id"] = new_id("key")
        data["tenant_id"] = tenant_id
        data["key_prefix"] = key_display_prefix(raw)
        data["key_hash"] = hash_api_key(raw)
        data["status"] = "active"
        request.state._omnimsg_api_key_plaintext = raw

    async def after_model_change(
        self,
        data: dict[str, Any],
        model: Any,
        is_created: bool,
        request: Request,
    ) -> Response | None:
        if not is_created:
            return None
        plaintext = getattr(request.state, "_omnimsg_api_key_plaintext", None)
        if isinstance(plaintext, str) and plaintext:
            Secret.reveal_once(
                request,
                plaintext,
                title="API key created",
                label=(
                    "Copy this API key now. It will not be shown again "
                    "after you leave this page."
                ),
            )
        meta = audit_meta(request)
        record_audit(
            actor=actor(request),
            action="apikey_create",
            entity_type="ApiKey",
            entity_id=getattr(model, "id", None),
            before=None,
            after=key_public_snapshot(model) if model is not None else None,
            **meta,
        )
        return None

    def _redirect_list(
        self, request: Request, *, error: str | None = None
    ) -> RedirectResponse:
        url = str(request.url_for("admin:list", identity=self.identity))
        if error:
            url = f"{url}?error={quote(error)}"
        return RedirectResponse(url)

    def _take_single_pk(self, request: Request) -> str | None:
        pks = [p for p in request.query_params.get("pks", "").split(",") if p]
        if len(pks) != 1:
            return None
        return pks[0]

    @action(
        name="deactivate",
        label="Deactivate",
        confirmation_message=(
            "Deactivate selected API key? Clients using this key will lose access "
            "immediately (replacement keys mid-grace cannot be deactivated this way)."
        ),
    )
    async def deactivate_keys(self, request: Request) -> Response:
        if get_settings().admin_read_only:
            return self._redirect_list(request)

        pk = self._take_single_pk(request)
        if pk is None:
            return self._redirect_list(
                request, error="Select exactly one API key to deactivate"
            )

        meta = audit_meta(request)
        factory = get_session_factory()
        try:
            with factory() as session:
                before_row = session.get(ApiKey, pk)
                before = key_public_snapshot(before_row) if before_row else None
                row = deactivate_api_key(session, key_id=pk)
                session.commit()
                after = key_public_snapshot(row)
            action_name = (
                "apikey_rotate_finish"
                if (
                    before
                    and before.get("replaced_by_key_id")
                    and after.get("status") == "inactive"
                )
                else "apikey_deactivate"
            )
            record_audit(
                actor=actor(request),
                action=action_name,
                entity_type="ApiKey",
                entity_id=pk,
                before=before,
                after=after,
                **meta,
            )
        except ApiKeyLifecycleError as exc:
            return self._redirect_list(request, error=exc.message)

        return self._redirect_list(request)

    @action(
        name="rotate-start",
        label="Start rotation",
        confirmation_message=(
            "Start two-step rotation? A new key will be created and shown once; "
            "the old key stays valid until the configured grace period ends "
            "(ADMIN_API_KEY_GRACE_HOURS), then finish rotation to revoke it."
        ),
    )
    async def rotate_start_action(self, request: Request) -> Response:
        if get_settings().admin_read_only:
            return self._redirect_list(request)

        pk = self._take_single_pk(request)
        if pk is None:
            return self._redirect_list(
                request, error="Select exactly one API key to rotate"
            )

        settings = get_settings()
        meta = audit_meta(request)
        factory = get_session_factory()
        try:
            with factory() as session:
                before_row = session.get(ApiKey, pk)
                before = key_public_snapshot(before_row) if before_row else None
                result = start_rotation(
                    session,
                    old_key_id=pk,
                    grace_hours=settings.admin_api_key_grace_hours,
                )
                session.commit()
                old_snap = key_public_snapshot(result.old)
                new_snap = key_public_snapshot(result.new)
                new_id = result.new.id
                plaintext = result.plaintext
                grace_iso = result.grace_expires_at.isoformat()
            record_audit(
                actor=actor(request),
                action="apikey_rotate_start",
                entity_type="ApiKey",
                entity_id=pk,
                before=before,
                after={
                    "old": old_snap,
                    "new": new_snap,
                    "grace_expires_at": grace_iso,
                    "grace_hours": settings.admin_api_key_grace_hours,
                },
                **meta,
            )
        except ApiKeyLifecycleError as exc:
            return self._redirect_list(request, error=exc.message)

        request.session[_REVEAL_SESSION_KEY] = {
            "key_id": new_id,
            "plaintext": plaintext,
            "old_key_id": pk,
            "grace_expires_at": grace_iso,
        }
        return RedirectResponse(
            str(request.url_for(f"admin:view-{self.identity}-reveal"))
        )

    @action(
        name="rotate-finish",
        label="Finish rotation",
        confirmation_message=(
            "Finish rotation and revoke the OLD key now? "
            "The replacement key remains active. Prefer waiting until grace expires "
            "unless you are sure clients have switched."
        ),
    )
    async def rotate_finish_action(self, request: Request) -> Response:
        if get_settings().admin_read_only:
            return self._redirect_list(request)

        pk = self._take_single_pk(request)
        if pk is None:
            return self._redirect_list(
                request,
                error="Select exactly one (old) API key to finish rotation",
            )

        meta = audit_meta(request)
        factory = get_session_factory()
        try:
            with factory() as session:
                before_row = session.get(ApiKey, pk)
                before = key_public_snapshot(before_row) if before_row else None
                row = finish_rotation(session, old_key_id=pk)
                session.commit()
                after = key_public_snapshot(row)
            record_audit(
                actor=actor(request),
                action="apikey_rotate_finish",
                entity_type="ApiKey",
                entity_id=pk,
                before=before,
                after=after,
                **meta,
            )
        except ApiKeyLifecycleError as exc:
            return self._redirect_list(request, error=exc.message)

        return self._redirect_list(request)

    @expose("/reveal", methods=["GET"])
    async def reveal(self, request: Request) -> Response:
        """One-shot plaintext page after rotate_start (session-backed)."""
        payload = request.session.pop(_REVEAL_SESSION_KEY, None)
        list_url = str(request.url_for("admin:list", identity=self.identity))
        if not isinstance(payload, dict) or "plaintext" not in payload:
            html = f"""<!DOCTYPE html>
<html><head><title>API key already shown</title>
<meta http-equiv="Cache-Control" content="no-store"/>
</head><body style="font-family:system-ui;margin:2rem">
<h1>API key no longer available</h1>
<p>The plaintext was shown once and cannot be retrieved again.</p>
<p><a href="{list_url}">Back to API Keys</a></p>
</body></html>"""
            response = HTMLResponse(html, status_code=410)
            Secret.apply_no_store_headers(response)
            return response

        plaintext = str(payload["plaintext"])
        key_id = str(payload.get("key_id", ""))
        old_key_id = str(payload.get("old_key_id", ""))
        grace = str(payload.get("grace_expires_at", ""))
        html = f"""<!DOCTYPE html>
<html><head><title>New API key — copy now</title>
<meta http-equiv="Cache-Control" content="no-store"/>
<style>
body{{font-family:system-ui,sans-serif;margin:2rem;background:#0f1419;color:#e7ecf3}}
code{{display:block;padding:1rem;background:#1a2332;border-radius:8px;word-break:break-all}}
.muted{{color:#8b9bb4}} a{{color:#79b8ff}}
.warn{{color:#ffcc66}}
</style></head><body>
<h1>New API key created</h1>
<p class="warn">Copy this value now. Refreshing or leaving this page permanently
hides it.</p>
<p class="muted">New key id: <strong>{key_id}</strong><br/>
Replaces: <strong>{old_key_id}</strong><br/>
Grace ends: <strong>{grace}</strong></p>
<code id="secret">{plaintext}</code>
<p><a href="{list_url}">Back to API Keys</a></p>
</body></html>"""
        response = HTMLResponse(html)
        Secret.apply_no_store_headers(response)
        return response
