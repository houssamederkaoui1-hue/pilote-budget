"""Debt endpoints (tracking + roll-ups)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.base import MessageResponse
from app.schemas.debt import DebtCreate, DebtResponse, DebtTotalsResponse, DebtUpdate
from app.services.debt_service import DebtService

router = APIRouter(tags=["debts"])


@router.get("/debts", response_model=list[DebtResponse])
def list_debts(session: Session = Depends(get_db)) -> list[DebtResponse]:
    return [DebtResponse(**item) for item in DebtService(session).list()]


@router.get("/debts/totals", response_model=DebtTotalsResponse)
def debt_totals(session: Session = Depends(get_db)) -> DebtTotalsResponse:
    return DebtTotalsResponse(**DebtService(session).totals())


@router.post("/debts", response_model=DebtResponse, status_code=status.HTTP_201_CREATED)
def create_debt(payload: DebtCreate, session: Session = Depends(get_db)) -> DebtResponse:
    return DebtResponse(**DebtService(session).create(**payload.model_dump()))


@router.get("/debts/{debt_id}", response_model=DebtResponse)
def get_debt(debt_id: int, session: Session = Depends(get_db)) -> DebtResponse:
    return DebtResponse(**DebtService(session).get(debt_id))


@router.patch("/debts/{debt_id}", response_model=DebtResponse)
def update_debt(
    debt_id: int, payload: DebtUpdate, session: Session = Depends(get_db)
) -> DebtResponse:
    fields = payload.model_dump(exclude_unset=True)
    return DebtResponse(**DebtService(session).update(debt_id, **fields))


@router.delete("/debts/{debt_id}", response_model=MessageResponse)
def delete_debt(debt_id: int, session: Session = Depends(get_db)) -> MessageResponse:
    DebtService(session).delete(debt_id)
    return MessageResponse(message="Debt deleted")