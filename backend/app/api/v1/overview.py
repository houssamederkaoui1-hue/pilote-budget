"""Financial overview endpoint (assets / liabilities / net worth)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.overview import OverviewResponse
from app.services.overview_service import OverviewService

router = APIRouter(tags=["overview"])


@router.get("/overview", response_model=OverviewResponse)
def get_overview(session: Session = Depends(get_db)) -> OverviewResponse:
    return OverviewResponse(**OverviewService(session).get())