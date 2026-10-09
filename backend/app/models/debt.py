"""Basic debt tracking."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, MoneyAmount, OptionalMoneyAmount, TimestampMixin

if TYPE_CHECKING:
    from app.models.account import Account


class Debt(Base, TimestampMixin):
    """A liability (loan, credit card balance, ...) being tracked.

    ``interest_rate`` is the annual percentage rate (e.g. 19.9 for 19.9% APR).
    ``account_id`` optionally links the debt to the account it lives in (for
    example a credit card account), so balance roll-ups stay consistent.
    """

    __tablename__ = "debts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    creditor: Mapped[str | None] = mapped_column(String(120), nullable=True)
    original_amount: Mapped[MoneyAmount] = mapped_column()
    remaining_amount: Mapped[MoneyAmount] = mapped_column()
    interest_rate: Mapped[float | None] = mapped_column(
        Numeric(6, 3, asdecimal=False), nullable=True
    )
    minimum_payment: Mapped[OptionalMoneyAmount] = mapped_column(default=None)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    account: Mapped[Account | None] = relationship("Account", lazy="selectin")
