"""Engine, session factory and FastAPI database dependency."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _lock_down_sqlite_file(settings: Settings) -> None:
    """Keep the on-disk database private (owner read/write only)."""
    url = settings.resolved_database_url
    if not url.startswith("sqlite:///"):
        return
    path_part = url[len("sqlite:///") :]
    if not path_part or path_part in {":memory:", ""}:
        return
    db_path = Path(path_part)
    try:
        if db_path.exists():
            db_path.chmod(0o600)
        if db_path.parent.exists():
            db_path.parent.chmod(0o700)
    except OSError:
        # Permissions hardening is best-effort; never let it crash the app.
        pass


def _build_engine(settings: Settings) -> Engine:
    url = settings.resolved_database_url
    kwargs: dict = {"future": True}
    if url.startswith("sqlite"):
        # SQLite lives in a single file/thread: allow FastAPI's worker threads
        # and keep referential integrity enabled.
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # Server databases (Postgres on Render): tolerate idle-connection
        # drops between requests (pool_pre_ping) and recycle long-lived
        # connections before the server kills them.
        kwargs["pool_pre_ping"] = True
        kwargs["pool_recycle"] = 1800
    engine = create_engine(url, **kwargs)

    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _configure_sqlite(dbapi_connection, _record):  # pragma: no cover
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    if url.startswith("sqlite:///"):
        _lock_down_sqlite_file(settings)

    return engine


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = _build_engine(get_settings())
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(), autoflush=False, expire_on_commit=False, future=True
        )
    return _session_factory


def reset_engine() -> None:
    """Dispose and drop cached engine/session factory (used by tests)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ping(engine: Engine | None = None) -> bool:
    """Cheap connectivity check used by the health endpoint."""
    engine = engine or get_engine()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return True
