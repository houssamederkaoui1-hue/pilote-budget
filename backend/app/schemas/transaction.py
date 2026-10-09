"""Transaction/transfer/list/summary schemas.

List responses merge transactions and transfers, so every row carries an
``entity`` discriminator plus both account references (transfers populate
``destination_account_id``; plain transactions leave it null).
"""

from __future__ import annotations

from datetime import date as Date, datetime

from pydantic import Field

from app.domain.enums import (
    TransactionStatus,
    TransactionType,
    TransferStatus,
)
from app.schemas.base import APIModel


class TransactionCreate(APIModel):
    type: TransactionType
    amount: float = Field(gt=0)
    account_id: int
    date: Date
    category_id: int | None = None
    destination_account_id: int | None = None  # transfers only
    description: str = Field(default="", max_length=255)
    notes: str | None = None
    status: TransactionStatus = TransactionStatus.CLEARED


class TransactionUpdate(APIModel):
    type: TransactionType | None = None
    amount: float | None = Field(default=None, gt=0)
    account_id: int | None = None
    date: Date | None = None
    category_id: int | None = None
    description: str | None = Field(default=None, max_length=255)
    notes: str | None = None
    status: TransactionStatus | None = None


class TransferCreate(APIModel):
    source_account_id: int
    destination_account_id: int
    amount: float = Field(gt=0)
    date: Date
    description: str = Field(default="", max_length=255)
    notes: str | None = None
    status: TransferStatus = TransferStatus.COMPLETED


class TransferUpdate(APIModel):
    source_account_id: int | None = None
    destination_account_id: int | None = None
    amount: float | None = Field(default=None, gt=0)
    date: Date | None = None
    description: str | None = Field(default=None, max_length=255)
    notes: str | None = None
    status: TransferStatus | None = None


class TransactionResponse(APIModel):
    """A merged ledger row (transaction or transfer)."""

    id: int
    entity: str  # "transaction" | "transfer"
    type: str  # income | expense | transfer
    amount: float
    date: Date
    description: str
    notes: str | None
    status: str
    account_id: int
    account_name: str | None
    category_id: int | None
    category_name: str | None
    destination_account_id: int | None
    destination_account_name: str | None
    created_at: datetime
    updated_at: datetime


class TransactionListResponse(APIModel):
    items: list[TransactionResponse]
    total: int
    limit: int
    offset: int


class SummaryResponse(APIModel):
    income: float
    expense: float
    net: float
    transfer_volume: float
