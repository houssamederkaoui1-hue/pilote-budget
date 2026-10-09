"""Quick Add / suggestion API schemas."""

from __future__ import annotations

from datetime import date as Date

from pydantic import Field

from app.domain.enums import TransactionStatus, TransactionType
from app.schemas.base import APIModel
from app.schemas.transaction import TransactionResponse


class CategorySuggestion(APIModel):
    category_id: int
    category_name: str
    confidence: str  # exact | similar | popular
    evidence: str | None = None
    score: float | None = None


class DuplicateMatch(APIModel):
    id: int
    account_id: int
    date: str
    amount: float
    description: str
    same_day: bool
    days_apart: int


class QuickCaptureRequest(APIModel):
    type: TransactionType
    amount: float = Field(gt=0)
    description: str = Field(default="", max_length=255)
    date: Date
    account_id: int | None = None
    category_id: int | None = None
    notes: str | None = None
    status: TransactionStatus = TransactionStatus.CLEARED


class QuickCaptureResponse(APIModel):
    type: str
    amount: float
    date: Date
    account_id: int | None
    category_id: int | None
    description: str
    categories: list[CategorySuggestion] = []
    duplicates: list[DuplicateMatch] = []
    warnings: list[str] = []


class QuickSuggestionRequest(APIModel):
    type: TransactionType
    amount: float = Field(gt=0)
    description: str = Field(default="", max_length=255)
    date: Date | None = None
    account_id: int | None = None


class QuickCreateRequest(APIModel):
    type: TransactionType
    amount: float = Field(gt=0)
    description: str = Field(default="", max_length=255)
    date: Date | None = None
    account_id: int | None = None
    category_id: int | None = None
    notes: str | None = None
    reject_duplicate: bool = False
    check_duplicate: bool = True


class QuickCreateResponse(APIModel):
    transaction: TransactionResponse
    duplicates: list[DuplicateMatch] = []
    warnings: list[str] = []