"""Domain enums shared by models, services and API schemas.

Pure Python only: no SQLAlchemy or FastAPI imports allowed here so the
calculation/domain layer stays framework independent.
"""

from __future__ import annotations

from enum import StrEnum


class AccountType(StrEnum):
    BANK = "bank"
    CHECKING = "checking"
    SAVINGS = "savings"
    CASH = "cash"
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    INVESTMENT = "investment"
    LOAN = "loan"
    OTHER = "other"


class AccountKind(StrEnum):
    """High level grouping used by analytics (asset vs liability)."""

    ASSET = "asset"
    LIABILITY = "liability"


class TransactionType(StrEnum):
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"


class TransactionStatus(StrEnum):
    PENDING = "pending"
    CLEARED = "cleared"
    RECONCILED = "reconciled"
    VOID = "void"


class CategoryType(StrEnum):
    INCOME = "income"
    EXPENSE = "expense"


class TransferStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class RecurrenceFrequency(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    CUSTOM = "custom"


class GoalStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
