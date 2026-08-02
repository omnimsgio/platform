"""API key usability and two-step rotation (ADR-0022 C2.2)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from omnimsg_common.auth import generate_api_key, hash_api_key, key_display_prefix
from omnimsg_common.db.models import ApiKey, Tenant
from omnimsg_common.ids import new_id


class ApiKeyLifecycleError(Exception):
    """Domain error for API key create / rotate / deactivate."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def api_key_is_usable(row: ApiKey, *, now: datetime | None = None) -> bool:
    """Return True if the key may authenticate right now.

    Old keys in an open rotation remain usable until ``grace_expires_at``;
    after that instant they are rejected even if ``status`` is still ``active``.
    """
    if row.status != "active":
        return False
    if row.replaced_by_key_id is None:
        return True
    if row.grace_expires_at is None:
        # Rotation marked but no grace window — treat as already revoked.
        return False
    clock = now or datetime.now(UTC)
    grace = row.grace_expires_at
    if grace.tzinfo is None:
        grace = grace.replace(tzinfo=UTC)
    return grace > clock


def find_open_rotation_for_tenant(
    session: Session, tenant_id: str
) -> ApiKey | None:
    """Return the old key of an unfinished rotation for this tenant, if any."""
    rows = session.scalars(
        select(ApiKey).where(
            ApiKey.tenant_id == tenant_id,
            ApiKey.replaced_by_key_id.is_not(None),
            ApiKey.status == "active",
        )
    ).all()
    return rows[0] if rows else None


def require_active_tenant(session: Session, tenant_id: str) -> Tenant:
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise ApiKeyLifecycleError("tenant_not_found", f"Tenant {tenant_id} not found")
    if tenant.status != "active":
        raise ApiKeyLifecycleError("tenant_inactive", f"Tenant {tenant_id} is inactive")
    return tenant


@dataclass(frozen=True)
class CreatedApiKey:
    row: ApiKey
    plaintext: str


def create_api_key(session: Session, *, tenant_id: str) -> CreatedApiKey:
    """Create a new active API key; plaintext returned once to the caller."""
    require_active_tenant(session, tenant_id)
    raw = generate_api_key()
    row = ApiKey(
        id=new_id("key"),
        tenant_id=tenant_id,
        key_prefix=key_display_prefix(raw),
        key_hash=hash_api_key(raw),
        status="active",
    )
    session.add(row)
    session.flush()
    return CreatedApiKey(row=row, plaintext=raw)


@dataclass(frozen=True)
class RotationStart:
    old: ApiKey
    new: ApiKey
    plaintext: str
    grace_expires_at: datetime


def start_rotation(
    session: Session,
    *,
    old_key_id: str,
    grace_hours: int,
) -> RotationStart:
    """Start two-phase rotation: new key active, old remains until grace ends."""
    if grace_hours < 1:
        raise ApiKeyLifecycleError("invalid_grace", "grace_hours must be >= 1")

    old = session.get(ApiKey, old_key_id)
    if old is None:
        raise ApiKeyLifecycleError("key_not_found", f"API key {old_key_id} not found")
    if old.status != "active":
        raise ApiKeyLifecycleError("key_inactive", "Cannot rotate an inactive API key")
    if old.replaced_by_key_id is not None:
        raise ApiKeyLifecycleError(
            "rotation_already_active",
            "This key already has an open rotation; finish it first",
        )

    open_rot = find_open_rotation_for_tenant(session, old.tenant_id)
    if open_rot is not None:
        raise ApiKeyLifecycleError(
            "rotation_already_active",
            f"Tenant already has an open rotation on {open_rot.id}",
        )

    require_active_tenant(session, old.tenant_id)

    created = create_api_key(session, tenant_id=old.tenant_id)
    new = created.row
    new.replaces_key_id = old.id
    grace_expires_at = datetime.now(UTC) + timedelta(hours=grace_hours)
    old.replaced_by_key_id = new.id
    old.grace_expires_at = grace_expires_at
    session.add(old)
    session.add(new)
    session.flush()
    return RotationStart(
        old=old,
        new=new,
        plaintext=created.plaintext,
        grace_expires_at=grace_expires_at,
    )


def finish_rotation(session: Session, *, old_key_id: str) -> ApiKey:
    """Revoke the old key after rotate_start (may be early or after grace)."""
    old = session.get(ApiKey, old_key_id)
    if old is None:
        raise ApiKeyLifecycleError("key_not_found", f"API key {old_key_id} not found")
    if old.replaced_by_key_id is None:
        raise ApiKeyLifecycleError(
            "no_active_rotation",
            "No open rotation on this key to finish",
        )
    if old.status != "active":
        raise ApiKeyLifecycleError(
            "no_active_rotation",
            "Rotation already finished (old key inactive)",
        )

    old.status = "inactive"
    # Keep replaced_by_key_id / grace_expires_at for audit trail.
    session.add(old)
    session.flush()
    return old


def deactivate_api_key(session: Session, *, key_id: str) -> ApiKey:
    """Deactivate a key; refuse if it is the replacement mid-grace."""
    key = session.get(ApiKey, key_id)
    if key is None:
        raise ApiKeyLifecycleError("key_not_found", f"API key {key_id} not found")
    if key.status != "active":
        return key

    predecessor = session.scalars(
        select(ApiKey).where(
            ApiKey.replaced_by_key_id == key.id,
            ApiKey.status == "active",
        )
    ).first()
    if predecessor is not None:
        raise ApiKeyLifecycleError(
            "cannot_deactivate_replacement",
            "Cannot deactivate the new key during an open rotation; "
            "finish the rotation on the old key instead",
        )

    # Early revoke of old key mid-rotation ≡ finish_rotation.
    if key.replaced_by_key_id is not None:
        return finish_rotation(session, old_key_id=key.id)

    key.status = "inactive"
    session.add(key)
    session.flush()
    return key


def key_public_snapshot(row: ApiKey) -> dict[str, Any]:
    """Audit-safe dict (never includes key_hash or plaintext)."""
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "key_prefix": row.key_prefix,
        "status": row.status,
        "replaced_by_key_id": row.replaced_by_key_id,
        "replaces_key_id": row.replaces_key_id,
        "grace_expires_at": (
            row.grace_expires_at.isoformat() if row.grace_expires_at else None
        ),
    }
