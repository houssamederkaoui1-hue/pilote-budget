"""Category schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.domain.enums import CategoryType
from app.schemas.base import APIModel


class CategoryCreate(APIModel):
    name: str = Field(min_length=1, max_length=120)
    type: CategoryType
    parent_id: int | None = None
    description: str | None = None
    active: bool = True


class CategoryUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    type: CategoryType | None = None
    parent_id: int | None = None
    description: str | None = None
    active: bool | None = None


class CategoryResponse(APIModel):
    id: int
    name: str
    type: CategoryType
    parent_id: int | None
    active: bool
    description: str | None
    created_at: datetime
    updated_at: datetime
