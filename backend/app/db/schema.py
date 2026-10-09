"""Schema creation / migration entry points.

Strategy:
- **Alembic is the source of truth** for SQLite (``alembic upgrade head``).
- **Postgres deployments** build the schema straight from the models with
  ``Base.metadata.create_all()`` (the model types are the source of truth for
  the deployed dialect) and then stamp the Alembic version to ``head`` so
  future revisions apply on top. The legacy SQLite-only migrations are never
  executed against Postgres.
- ``ensure_schema()`` runs on application startup so a fresh checkout works
  with a single command; it can be disabled with ``PILOTE_AUTO_MIGRATE=false``.
- ``create_all()`` exists for throwaway databases (tests, scratch work).
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

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


def ensure_postgres(settings: Settings) -> None:
    """Create the Postgres schema from the models and stamp Alembic at head."""
    from alembic import command as alembic_command

    from app.db.base import Base
    from app.db.session import get_engine
    from app import models  # noqa: F401  (registers models on Base.metadata)

    engine = get_engine()
    Base.metadata.create_all(engine)

    current: str | None = None
    with engine.connect() as connection:
        if inspect(connection).has_table("alembic_version"):
            current = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar()
    if not current:
        # Mark the create_all'd schema as "head" so future Alembic revisions
        # apply on top without trying to replay the SQLite-only chain.
        alembic_command.stamp(alembic_config(settings.resolved_database_url), "head")


def ensure_schema(settings: Settings | None = None) -> None:
    """Bring the database in line with the application's schema."""
    settings = settings or get_settings()
    if not settings.auto_migrate:
        return
    url = settings.resolved_database_url
    if url.startswith("postgresql"):
        ensure_postgres(settings)
        return
    if url.startswith("sqlite:///"):
        path_part = url.replace("sqlite:///", "")
        if path_part not in {":memory:", ""}:
            Path(path_part).parent.mkdir(parents=True, exist_ok=True)
    run_migrations(url)
