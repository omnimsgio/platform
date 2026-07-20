"""Shared fixtures for API-phase tests (Postgres + Redis when available)."""

from __future__ import annotations

import os

import pytest
from omnimsg_common.auth import generate_api_key, hash_api_key, key_display_prefix
from omnimsg_common.db.migrate import main as migrate_main
from omnimsg_common.db.models import ApiKey, Base, Tenant
from omnimsg_common.db.session import get_engine, reset_engine, session_scope
from omnimsg_common.ids import new_id
from omnimsg_common.settings import get_settings
from sqlalchemy import text
from sqlalchemy.exc import OperationalError


def pytest_configure() -> None:
    # Prefer CI/local service defaults when unset.
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql://omnimsgio:omnimsgio@localhost:5432/omnimsgio",
    )
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/3")
    os.environ.setdefault("REDIS_KEY_PREFIX", "omnimsgio:")
    os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "60")
    get_settings.cache_clear()
    reset_engine()


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _postgres_available() -> bool:
    try:
        reset_engine()
        get_settings.cache_clear()
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


@pytest.fixture(scope="session")
def postgres_ready() -> bool:
    if not _postgres_available():
        pytest.skip("Postgres not available (set DATABASE_URL / start CI service)")
    migrate_main(["upgrade", "head"])
    return True


@pytest.fixture
def db_clean(postgres_ready: bool) -> None:
    """Truncate app tables between tests."""
    del postgres_ready
    engine = get_engine()
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    yield


@pytest.fixture
def seeded_tenant(db_clean: None) -> dict[str, str]:
    """Insert an active tenant + API key; return ids and plaintext key."""
    del db_clean
    tenant_id = "ten_test"
    raw_key = generate_api_key()
    key_id = new_id("key")
    with session_scope() as session:
        session.add(Tenant(id=tenant_id, name="Test Tenant", status="active"))
        session.add(
            ApiKey(
                id=key_id,
                tenant_id=tenant_id,
                key_prefix=key_display_prefix(raw_key),
                key_hash=hash_api_key(raw_key),
                status="active",
            )
        )
    return {
        "tenant_id": tenant_id,
        "api_key_id": key_id,
        "api_key": raw_key,
    }
