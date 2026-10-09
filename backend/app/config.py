from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

BASE_DIR = Path(__file__).resolve().parent.parent


class _BareDatabaseUrlSource(PydanticBaseSettingsSource):
    """Fall back to a bare ``DATABASE_URL`` env var (the Render convention).

    Lower priority than every ``PILOTE_*`` source, so setting
    ``PILOTE_DATABASE_URL`` explicitly always wins.
    """

    def get_field_value(self, field, field_name: str):
        if field_name == "database_url":
            value = os.environ.get("DATABASE_URL")
            if value is not None:
                return value, field_name, False
        return None, field_name, False

    def __call__(self) -> dict[str, object]:
        value = os.environ.get("DATABASE_URL")
        if value:
            return {"database_url": value}
        return {}


class Settings(BaseSettings):
    """Application configuration.

    Values are resolved from (in order): environment variables prefixed with
    ``PILOTE_``, an optional ``.env`` file, then the defaults below. A bare
    ``DATABASE_URL`` (Render's managed-Postgres variable) is honoured as a
    final fallback for ``database_url`` only.
    """

    model_config = SettingsConfigDict(
        env_prefix="PILOTE_",
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Pilote Budget API"
    version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False

    # SQLite database location. Relative paths resolve against the backend dir.
    database_url: str = "sqlite:///./data/pilote_budget.db"
    auto_create_tables: bool = True
    auto_migrate: bool = True

    api_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default=["http://localhost:5173", "http://127.0.0.1:5173"])

    # When set, every API route (except the public ``/config`` bootstrap and
    # ``/health`` health check) requires ``Authorization: Bearer <token>``.
    access_token: str | None = None

    # Serve the built frontend (``frontend/dist``) from the API, same origin.
    # This is how the deployed app is hosted: one origin, automatic HTTPS, no
    # cross-origin calls. Off by default so local dev keeps using Vite.
    serve_frontend: bool = False
    frontend_dist: Path = BASE_DIR.parent / "frontend" / "dist"

    @field_validator("cors_origins")
    @classmethod
    def _reject_wildcard_origin(cls, origins: list[str]) -> list[str]:
        for origin in origins or []:
            if origin == "*":
                raise ValueError(
                    "PILOTE_CORS_ORIGINS must not contain '*' "
                    "(local-first apps should use explicit origins)"
                )
        return origins

    @property
    def is_test(self) -> bool:
        return self.environment == "test"

    @property
    def auth_enabled(self) -> bool:
        """True when a shared access token protects the API."""
        return bool(self.access_token)

    @property
    def resolved_database_url(self) -> str:
        """Return an absolute URL, normalise the Postgres driver, and make
        sure the SQLite parent folder exists."""
        raw = self.database_url.strip()
        if raw.startswith("sqlite"):
            prefix = "sqlite:///"
            path_part = raw[len(prefix) :]
            if path_part in {":memory:", ""}:
                return raw
            path = Path(path_part)
            if not path.is_absolute():
                path = (BASE_DIR / path).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            return f"{prefix}{path}"
        # Render/Heroku-style `postgres://` / `postgresql://` URLs use psycopg3.
        match = re.match(r"^(postgres|postgresql)://", raw)
        if match:
            return "postgresql+psycopg" + raw[match.end() - 3 :]
        return raw

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # First source has the highest priority; the bare DATABASE_URL fallback
        # intentionally comes last so PILOTE_* settings always win.
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
            _BareDatabaseUrlSource(settings_cls),
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()