"""Budget schemas (allocation + per-category, with the engine's computed view)."""

from __future__ import annotations

from datetime import date

from pydantic import Field

from app.schemas.base import APIModel


class AllocationPut(APIModel):
    income: float | None = Field(default=None, ge=0)
    needs: float | None = Field(default=None, ge=0)
    wants: float | None = Field(default=None, ge=0)
    savings: float | None = Field(default=None, ge=0)
    other: float | None = Field(default=None, ge=0)


class BudgetItemPut(APIModel):
    category_id: int
    planned_amount: float = Field(ge=0)
    notes: str | None = None


class BudgetPut(APIModel):
    """``null`` allocation/items deletes that half of the plan."""

    allocation: AllocationPut | None = None
    items: list[BudgetItemPut] = Field(default_factory=list)


class AllocationStats(APIModel):
    income_amount: float
    planned_total: float
    actual_total: float
    remaining_total: float
    pct_used: float | None
    over_budget: bool
    has_allocation: bool
    needs_amount: float
    wants_amount: float
    savings_amount: float
    other_amount: float


class BudgetItemStats(APIModel):
    category_id: int
    category_name: str
    planned_amount: float
    actual_amount: float
    remaining_amount: float
    pct_used: float | None
    over_budget: bool
    status: str  # over | approaching | healthy | none
    notes: str | None = None


class BudgetTotals(APIModel):
    planned: float
    actual: float
    remaining: float
    pct_used: float | None
    over_budget: bool


class BudgetResponse(APIModel):
    period_start: date
    period_end: date
    month_start_day: int
    allocation: AllocationStats
    items: list[BudgetItemStats]
    totals: BudgetTotals
    approaching: list[int]
    exceeding: list[int]