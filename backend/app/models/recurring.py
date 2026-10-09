"""Recurring transaction templates."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, MoneyAmount, TimestampMixin
from app.db.types import string_enum
from app.domain.enums import RecurrenceFrequency, TransactionType

if TYPE_CHECKING:
    from app.models.account import Account
    from app.models.category import Category


class RecurringTransaction(Base, TimestampMixin):
    """A template that will materialize transactions on a schedule.

    Only ``income``/``expense`` are used today; ``transfer`` is allowed by the
    type so scheduled internal transfers can be added later without a schema
    change.
    """

    __tablename__ = "recurring_transactions"
    __table_args__ = (Index("ix_recurring_active_next", "active", "next_occurrence"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    type: Mapped[TransactionType] = mapped_column(string_enum(TransactionType), nullable=False)
    amount: Mapped[MoneyAmount] = mapped_column()
    frequency: Mapped[RecurrenceFrequency] = mapped_column(
        string_enum(RecurrenceFrequency), nullable=False, default=RecurrenceFrequency.MONTHLY
    )
    next_occurrence: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default="")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")

    account: Mapped[Account] = relationship("Account", lazy="selectin")
    category: Mapped[Category | None] = relationship("Category", lazy="selectin")
