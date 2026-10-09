"""Recurring transaction schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from app.domain.enums import RecurrenceFrequency, TransactionType
from app.schemas.base import APIModel


class RecurringCreate(APIModel):
    account_id: int
    type: TransactionType
    amount: float = Field(gt=0)
    frequency: RecurrenceFrequency = RecurrenceFrequency.MONTHLY
    next_occurrence: date | None = None
    end_date: date | None = None
    category_id: int | None = None
    description: str = Field(default="", max_length=255)
    notes: str | None = None
    active: bool = True


class RecurringUpdate(APIModel):
    account_id: int | None = None
    type: TransactionType | None = None
    amount: float | None = Field(default=None, gt=0)
    frequency: RecurrenceFrequency | None = None
    next_occurrence: date | None = None
    end_date: date | None = None
    category_id: int | None = None
    description: str | None = Field(default=None, max_length=255)
    notes: str | None = None
    active: bool | None = None


class RecurringResponse(APIModel):
    id: int
    account_id: int
    account_name: str | None
    category_id: int | None
    category_name: str | None
    type: str
    amount: float
    frequency: str
    next_occurrence: date
    end_date: date | None
    description: str
    notes: str | None
    active: bool
    created_at: datetime
    updated_at: datetime


class RecurringOccurrence(APIModel):
    recurring_id: int
    due_date: date
    overdue: bool
    type: str
    amount: float
    frequency: str
    description: str
    account_id: int
    account_name: str | None
    category_id: int | None
    category_name: str | None
    end_date: date | None


class UpcomingResponse(APIModel):
    as_of: date
    horizon_days: int
    horizon_end: date
    occurrences: list[RecurringOccurrence]


class RecordResponse(APIModel):
    recurring_id: int
    date: date
    next_occurrence: date
    deactivated: bool
    template: RecurringResponse


class AdvanceResponse(APIModel):
    recurring_id: int
    next_occurrence: date
    deactivated: bool
    template: RecurringResponse