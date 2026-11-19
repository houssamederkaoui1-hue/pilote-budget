"""SQLite schema initialization and Alembic migration helpers."""

from __future__ import annotations

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.config import BASE_DIR, Settings, get_settings

MIGRATIONS_DIR = BASE_DIR / "alembic"


def alembic_config(database_url: str | None = None) -> Config:
    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    if database_url:
        cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return cfg


def run_migrations(database_url: str | None = None) -> None:
    """Upgrade the database to the latest revision."""
    url = database_url or get_settings().resolved_database_url
    command.upgrade(alembic_config(url), "head")


def create_all() -> None:
    """Create every table straight from the model metadata (no Alembic)."""
    from app.db.base import Base
    from app.db.session import get_engine
    from app import models  # noqa: F401  (registers models on Base.metadata)

    Base.metadata.create_all(get_engine())


def existing_tables() -> list[str]:
    from app.db.session import get_engine

    return sorted(inspect(get_engine()).get_table_names())


def ensure_schema(settings: Settings | None = None) -> None:
    """Bring the database in line with the application's schema."""
    settings = settings or get_settings()
    if settings.auto_migrate:
        run_migrations(settings.resolved_database_url)
