"""Goal schemas (persisted fields + engine-computed projections)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from app.schemas.base import APIModel


class GoalCreate(APIModel):
    name: str
    target_amount: float = Field(gt=0)
    current_amount: float = Field(default=0.0, ge=0)
    target_date: date | None = None
    account_id: int | None = None
    active: bool = True
    notes: str | None = None


class GoalUpdate(APIModel):
    name: str | None = None
    target_amount: float | None = Field(default=None, gt=0)
    current_amount: float | None = Field(default=None, ge=0)
    target_date: date | None = None
    account_id: int | None = None
    active: bool | None = None
    notes: str | None = None


class GoalResponse(APIModel):
    id: int
    name: str
    target_amount: float
    current_amount: float
    target_date: date | None
    account_id: int | None
    account_name: str | None
    active: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime
    # computed by the goal engine
    progress_pct: float
    remaining_amount: float
    required_monthly_saving: float | None
    monthly_contribution: float | None
    estimated_completion_date: date | None