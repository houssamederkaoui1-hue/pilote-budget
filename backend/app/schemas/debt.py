"""Debt schemas (basic tracking + roll-ups)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from app.schemas.base import APIModel


class DebtCreate(APIModel):
    name: str
    creditor: str | None = None
    original_amount: float = Field(ge=0)
    remaining_amount: float | None = Field(default=None, ge=0)
    interest_rate: float | None = Field(default=None, ge=0)
    minimum_payment: float | None = Field(default=None, ge=0)
    due_date: date | None = None
    account_id: int | None = None
    active: bool = True
    notes: str | None = None


class DebtUpdate(APIModel):
    name: str | None = None
    creditor: str | None = None
    original_amount: float | None = Field(default=None, ge=0)
    remaining_amount: float | None = Field(default=None, ge=0)
    interest_rate: float | None = Field(default=None, ge=0)
    minimum_payment: float | None = Field(default=None, ge=0)
    due_date: date | None = None
    account_id: int | None = None
    active: bool | None = None
    notes: str | None = None


class DebtResponse(APIModel):
    id: int
    name: str
    creditor: str | None
    original_amount: float
    remaining_amount: float
    interest_rate: float | None
    minimum_payment: float | None
    due_date: date | None
    account_id: int | None
    account_name: str | None
    active: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime


class UpcomingDue(APIModel):
    debt_id: int
    name: str
    due_date: date
    remaining_amount: float
    minimum_payment: float | None


class DebtTotalsResponse(APIModel):
    total_original: float
    total_remaining: float
    total_minimum_payment: float
    active_debt_count: int
    upcoming_due_dates: list[UpcomingDue]