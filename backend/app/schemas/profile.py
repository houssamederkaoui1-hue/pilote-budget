"""Profile (user settings) schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.schemas.base import APIModel


class ProfileResponse(APIModel):
    id: int
    currency: str
    month_start_day: int
    timezone: str
    preferences: dict[str, Any]
    created_at: datetime
    updated_at: datetime
