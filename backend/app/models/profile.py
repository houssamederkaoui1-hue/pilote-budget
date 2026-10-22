"""User profile / financial settings (single row table)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Profile(Base, TimestampMixin):
    """Application-wide user settings.

    There is only ever one row (``id == 1``); ``ProfileService`` creates it on
    first use with sensible defaults.
    """

    __tablename__ = "profiles"

    DEFAULT_ID = 1

    id: Mapped[int] = mapped_column(primary_key=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="MAD")
    month_start_day: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="UTC", server_default="UTC"
    )
    preferences: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
