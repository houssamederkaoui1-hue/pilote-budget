"""Shared pytest fixtures.

Every test runs against a throwaway SQLite database in a temp directory so a
clean environment is exercised each time.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.config import Settings, get_settings
from app.db.session import reset_engine


@pytest.fixture
def settings(tmp_path, monkeypatch) -> Iterator[Settings]:
    monkeypatch.setenv("PILOTE_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("PILOTE_ENVIRONMENT", "test")
    monkeypatch.setenv("PILOTE_AUTO_MIGRATE", "true")
    get_settings.cache_clear()
    reset_engine()

    yield get_settings()

    reset_engine()
    get_settings.cache_clear()


@pytest.fixture
def app(settings: Settings):
    from app.main import create_app

    return create_app(settings)


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    # The lifespan hook runs migrations, so the schema exists after entering.
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        yield test_client


@pytest.fixture
def session(settings: Settings) -> Iterator:
    from app.db.schema import ensure_schema
    from app.db.session import get_session_factory

    ensure_schema(settings)
    db_session = get_session_factory()()
    try:
        yield db_session
        db_session.commit()
    finally:
        db_session.close()
