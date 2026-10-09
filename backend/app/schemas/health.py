"""Health endpoint schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from app.schemas.base import APIModel


class DatabaseStatus(APIModel):
    connected: bool
    dialect: str | None = None


class HealthResponse(APIModel):
    status: Literal["ok", "degraded"]
    app: str
    version: str
    environment: str
    database: DatabaseStatus
    time: datetime
