"""Financial Assistant endpoints (insights overview + structured Q&A)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.financial_assistant import (
    AssistantAskRequest,
    AssistantAskResponse,
    AssistantOverviewResponse,
)
from app.services.financial_assistant_service import FinancialAssistantService

router = APIRouter(tags=["assistant"])


@router.get("/assistant", response_model=AssistantOverviewResponse)
def get_assistant(session: Session = Depends(get_db)) -> AssistantOverviewResponse:
    return AssistantOverviewResponse(**FinancialAssistantService(session).overview())


@router.post("/assistant/ask", response_model=AssistantAskResponse)
def ask_assistant(
    payload: AssistantAskRequest,
    session: Session = Depends(get_db),
) -> AssistantAskResponse:
    return AssistantAskResponse(
        **FinancialAssistantService(session).ask(
            payload.question,
            intent=payload.intent,
            goal_id=payload.goal_id,
        )
    )