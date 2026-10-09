"""Recurring transaction endpoints (templates + upcoming projection).

Static paths (``/recurring/upcoming``) are declared before the dynamic
``/recurring/{id}`` route.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.base import MessageResponse
from app.schemas.recurring import (
    AdvanceResponse,
    RecordResponse,
    RecurringCreate,
    RecurringResponse,
    RecurringUpdate,
    UpcomingResponse,
)
from app.services.recurring_service import RecurringService

router = APIRouter(tags=["recurring"])


@router.get("/recurring", response_model=list[RecurringResponse])
def list_recurring(session: Session = Depends(get_db)) -> list[RecurringResponse]:
    return [RecurringResponse(**item) for item in RecurringService(session).list()]


@router.get("/recurring/upcoming", response_model=UpcomingResponse)
def recurring_upcoming(
    days: int = Query(30, ge=1, le=365),
    session: Session = Depends(get_db),
) -> UpcomingResponse:
    return UpcomingResponse(**RecurringService(session).upcoming(date.today(), days))


@router.post("/recurring", response_model=RecurringResponse, status_code=status.HTTP_201_CREATED)
def create_recurring(
    payload: RecurringCreate, session: Session = Depends(get_db)
) -> RecurringResponse:
    return RecurringResponse(**RecurringService(session).create(**payload.model_dump()))


@router.get("/recurring/{recurring_id}", response_model=RecurringResponse)
def get_recurring(recurring_id: int, session: Session = Depends(get_db)) -> RecurringResponse:
    return RecurringResponse(**RecurringService(session).get(recurring_id))


@router.patch("/recurring/{recurring_id}", response_model=RecurringResponse)
def update_recurring(
    recurring_id: int, payload: RecurringUpdate, session: Session = Depends(get_db)
) -> RecurringResponse:
    fields = payload.model_dump(exclude_unset=True)
    return RecurringResponse(**RecurringService(session).update(recurring_id, **fields))


@router.post("/recurring/{recurring_id}/record", response_model=RecordResponse)
def record_recurring(
    recurring_id: int,
    date: date | None = Query(None, description="Posting date; defaults to next_occurrence"),
    session: Session = Depends(get_db),
) -> RecordResponse:
    return RecordResponse(**RecurringService(session).record(recurring_id, date))


@router.post("/recurring/{recurring_id}/advance", response_model=AdvanceResponse)
def advance_recurring(
    recurring_id: int, session: Session = Depends(get_db)
) -> AdvanceResponse:
    return AdvanceResponse(**RecurringService(session).advance(recurring_id))


@router.delete("/recurring/{recurring_id}", response_model=MessageResponse)
def delete_recurring(
    recurring_id: int, session: Session = Depends(get_db)
) -> MessageResponse:
    RecurringService(session).delete(recurring_id)
    return MessageResponse(message="Recurring template deleted")