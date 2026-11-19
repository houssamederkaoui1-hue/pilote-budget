from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Read PILOTE_ settings from the environment or backend/.env."""

    model_config = SettingsConfigDict(
        env_prefix="PILOTE_",
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    app_name: str = "Pilote Budget API"
    version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False

    database_url: str = "sqlite:///./data/pilote_budget.db"
    auto_migrate: bool = True
    api_prefix: str = "/api/v1"

    @field_validator("database_url")
    @classmethod
    def _require_sqlite_file(cls, value: str) -> str:
        error = "PILOTE_DATABASE_URL must point to a local SQLite file (sqlite:///path)"
        try:
            url = make_url(value.strip())
        except ArgumentError:
            raise ValueError(error) from None
        if (
            url.drivername not in {"sqlite", "sqlite+pysqlite"}
            or url.host is not None
            or url.port is not None
            or url.username is not None
            or url.password is not None
            or not url.database
            or url.database == ":memory:"
            or "uri" in url.query
        ):
            raise ValueError(error)
        return value.strip()

    @property
    def resolved_database_url(self) -> str:
        """Resolve relative paths against backend/ before opening SQLite."""
        url = make_url(self.database_url)
        path = (BASE_DIR / (url.database or "")).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return url.set(database=str(path)).render_as_string()


@lru_cache
def get_settings() -> Settings:
    return Settings()
