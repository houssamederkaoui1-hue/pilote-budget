"""Shared input validation for transaction-like records."""

from __future__ import annotations

import math
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.errors import NotFoundError, ValidationError
from app.models.account import Account
from app.models.category import Category

MIN_DATE = date(1900, 1, 1)
MAX_DATE = date(2200, 12, 31)
MAX_AMOUNT = 1_000_000_000_000.0


def validate_amount(value: float | int | None) -> float:
    if value is None:
        raise ValidationError("Amount is required")
    try:
        amount = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Amount must be a number") from exc
    if not math.isfinite(amount):
        raise ValidationError("Amount must be a finite number")
    if amount <= 0:
        raise ValidationError("Amount must be greater than zero")
    if amount > MAX_AMOUNT:
        raise ValidationError("Amount is unreasonably large")
    return round(amount, 2)


def validate_date(value: date | str | None) -> date:
    if value is None:
        raise ValidationError("Date is required")
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value)
        except ValueError as exc:
            raise ValidationError(f"Invalid date: {value!r} (expected YYYY-MM-DD)") from exc
    if not isinstance(value, date):
        raise ValidationError("Invalid date")
    if not (MIN_DATE <= value <= MAX_DATE):
        raise ValidationError(f"Date must be between {MIN_DATE} and {MAX_DATE}")
    return value


def validate_account(
    session: Session, account_id: int | None, *, require_active: bool = True
) -> Account:
    if account_id is None:
        raise ValidationError("Account is required")
    account = session.get(Account, account_id)
    if account is None:
        raise NotFoundError(f"Account {account_id} not found")
    if require_active and not account.active:
        raise ValidationError(f"Account '{account.name}' is archived")
    return account


def validate_category(
    session: Session, category_id: int | None, *, expected_type: str | None = None
) -> Category | None:
    if category_id is None:
        return None
    category = session.get(Category, category_id)
    if category is None:
        raise NotFoundError(f"Category {category_id} not found")
    if not category.active:
        raise ValidationError(f"Category '{category.name}' is archived")
    if expected_type is not None and category.type.value != expected_type:
        raise ValidationError(
            f"Category '{category.name}' is a '{category.type.value}' category "
            f"and cannot be used for {expected_type} transactions"
        )
    return category


def validate_description(value: str | None) -> str:
    cleaned = (value or "").strip()
    if len(cleaned) > 255:
        raise ValidationError("Description must be 255 characters or fewer")
    return cleaned


def validate_notes(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None


def validate_enum(value, enum_cls, label: str):
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(value)
    except ValueError as exc:
        allowed = ", ".join(member.value for member in enum_cls)
        raise ValidationError(f"Unknown {label} '{value}' (allowed: {allowed})") from exc
