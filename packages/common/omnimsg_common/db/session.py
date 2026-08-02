"""Engine and session factory for Postgres access."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from omnimsg_common.settings import Settings, get_settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def sqlalchemy_url(database_url: str) -> str:
    """Prefer the psycopg3 driver when a bare postgresql:// DSN is provided."""
    if database_url.startswith("postgresql+psycopg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url.removeprefix("postgresql://")
    if database_url.startswith("postgres://"):
        return "postgresql+psycopg://" + database_url.removeprefix("postgres://")
    return database_url


def get_engine(settings: Settings | None = None) -> Engine:
    """Return a process-wide SQLAlchemy engine (lazy singleton)."""
    global _engine, _session_factory
    if _engine is None:
        cfg = settings or get_settings()
        _engine = create_engine(
            sqlalchemy_url(cfg.database_url),
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    """Return a sessionmaker bound to the shared engine."""
    get_engine(settings)
    assert _session_factory is not None
    return _session_factory


def reset_engine() -> None:
    """Dispose the shared engine (for tests)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


@contextmanager
def session_scope(settings: Settings | None = None) -> Iterator[Session]:
    """Provide a transactional session scope that commits or rolls back."""
    factory = get_session_factory(settings)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
