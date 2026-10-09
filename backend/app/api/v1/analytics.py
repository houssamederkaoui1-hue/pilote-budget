"""Analytics endpoints (dashboard engine + Safe-to-Spend)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.analytics import AnalyticsResponse, SafeToSpendResponse
from app.services.analytics_service import AnalyticsService

router = APIRouter(tags=["analytics"])


@router.get("/analytics", response_model=AnalyticsResponse)
def get_analytics(
    months: int | None = Query(
        default=None, ge=1, le=12, description="History windows to include (dashboard period preference)."
    ),
    session: Session = Depends(get_db),
) -> AnalyticsResponse:
    return AnalyticsResponse(**AnalyticsService(session).summary(months=months))


@router.get("/analytics/safe-to-spend", response_model=SafeToSpendResponse)
def get_safe_to_spend(session: Session = Depends(get_db)) -> SafeToSpendResponse:
    return SafeToSpendResponse(**AnalyticsService(session).safe_to_spend())