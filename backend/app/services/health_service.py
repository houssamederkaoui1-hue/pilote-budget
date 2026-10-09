"""Health checks."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import Settings


class HealthService:
    def __init__(self, session: Session, settings: Settings):
        self.session = session
        self.settings = settings

    def check(self) -> dict:
        connected = True
        try:
            self.session.execute(text("SELECT 1"))
        except Exception:
            connected = False

        engine = self.session.get_bind()
        return {
            "status": "ok" if connected else "degraded",
            "app": self.settings.app_name,
            "version": self.settings.version,
            "environment": self.settings.environment,
            "database": {"connected": connected, "dialect": engine.dialect.name},
        }
