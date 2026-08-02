"""Unit tests for API key two-step rotation lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from omnimsg_common.api_key_lifecycle import (
    ApiKeyLifecycleError,
    api_key_is_usable,
    create_api_key,
    deactivate_api_key,
    finish_rotation,
    start_rotation,
)
from omnimsg_common.auth import hash_api_key
from omnimsg_common.db.models import ApiKey
from omnimsg_common.db.session import session_scope


def test_create_and_usable(seeded_tenant: dict[str, str]) -> None:
    with session_scope() as session:
        created = create_api_key(session, tenant_id=seeded_tenant["tenant_id"])
        assert created.plaintext.startswith("omni_")
        assert created.row.key_hash == hash_api_key(created.plaintext)
        assert "key_hash" not in created.plaintext
        assert api_key_is_usable(created.row)


def test_second_rotation_blocked(seeded_tenant: dict[str, str]) -> None:
    with session_scope() as session:
        old_id = seeded_tenant["api_key_id"]
        start_rotation(session, old_key_id=old_id, grace_hours=24)
        with pytest.raises(ApiKeyLifecycleError) as exc:
            start_rotation(session, old_key_id=old_id, grace_hours=24)
        assert exc.value.code == "rotation_already_active"


def test_finish_without_rotation_fails(seeded_tenant: dict[str, str]) -> None:
    with session_scope() as session:
        with pytest.raises(ApiKeyLifecycleError) as exc:
            finish_rotation(session, old_key_id=seeded_tenant["api_key_id"])
        assert exc.value.code == "no_active_rotation"


def test_cannot_deactivate_replacement_during_grace(
    seeded_tenant: dict[str, str],
) -> None:
    with session_scope() as session:
        result = start_rotation(
            session, old_key_id=seeded_tenant["api_key_id"], grace_hours=24
        )
        new_id = result.new.id
        with pytest.raises(ApiKeyLifecycleError) as exc:
            deactivate_api_key(session, key_id=new_id)
        assert exc.value.code == "cannot_deactivate_replacement"


def test_old_key_rejected_after_grace(seeded_tenant: dict[str, str]) -> None:
    with session_scope() as session:
        result = start_rotation(
            session, old_key_id=seeded_tenant["api_key_id"], grace_hours=1
        )
        old = session.get(ApiKey, seeded_tenant["api_key_id"])
        assert old is not None
        assert api_key_is_usable(old)

        # Simulate grace expiry without waiting.
        old.grace_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.add(old)
        session.flush()
        assert not api_key_is_usable(old)
        # Replacement still usable.
        assert api_key_is_usable(result.new)


def test_both_keys_valid_during_grace(seeded_tenant: dict[str, str]) -> None:
    with session_scope() as session:
        result = start_rotation(
            session, old_key_id=seeded_tenant["api_key_id"], grace_hours=24
        )
        old = session.get(ApiKey, seeded_tenant["api_key_id"])
        assert old is not None
        assert api_key_is_usable(old)
        assert api_key_is_usable(result.new)


def test_finish_revokes_old_keeps_new(seeded_tenant: dict[str, str]) -> None:
    with session_scope() as session:
        result = start_rotation(
            session, old_key_id=seeded_tenant["api_key_id"], grace_hours=24
        )
        new_id = result.new.id
        finish_rotation(session, old_key_id=seeded_tenant["api_key_id"])
        old = session.get(ApiKey, seeded_tenant["api_key_id"])
        new = session.get(ApiKey, new_id)
        assert old is not None and new is not None
        assert old.status == "inactive"
        assert not api_key_is_usable(old)
        assert new.status == "active"
        assert api_key_is_usable(new)
