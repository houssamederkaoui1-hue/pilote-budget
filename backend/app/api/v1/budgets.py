"""Budget endpoints (allocate + engine summary for a period)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.budget import BudgetPut, BudgetResponse
from app.services.budget_service import BudgetService

router = APIRouter(tags=["budgets"])


@router.get("/budgets", response_model=BudgetResponse)
def get_budget(
    period: date | None = Query(None, description="Any date in the budget period"),
    session: Session = Depends(get_db),
) -> BudgetResponse:
    anchor = period or date.today()
    return BudgetResponse(**BudgetService(session).summary(anchor))


@router.put("/budgets", response_model=BudgetResponse)
def put_budget(
    payload: BudgetPut,
    period: date | None = Query(None, description="Any date in the budget period"),
    session: Session = Depends(get_db),
) -> BudgetResponse:
    anchor = period or date.today()
    result = BudgetService(session).put(
        anchor,
        allocation=payload.allocation.model_dump() if payload.allocation else None,
        items=[item.model_dump() for item in payload.items],
    )
    return BudgetResponse(**result)