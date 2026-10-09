"""Account schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.domain.enums import AccountType
from app.schemas.base import APIModel


class AccountCreate(APIModel):
    name: str = Field(min_length=1, max_length=120)
    type: AccountType = AccountType.BANK
    opening_balance: float = 0.0
    currency: str | None = Field(default=None, max_length=3)
    description: str | None = None
    active: bool = True


class AccountUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    type: AccountType | None = None
    opening_balance: float | None = None
    currency: str | None = Field(default=None, max_length=3)
    description: str | None = None
    active: bool | None = None


class AccountResponse(APIModel):
    id: int
    name: str
    type: AccountType
    opening_balance: float
    current_balance: float
    currency: str | None
    active: bool
    description: str | None
    created_at: datetime
    updated_at: datetime
