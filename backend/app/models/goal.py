"""Savings goals."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, MoneyAmount, TimestampMixin

if TYPE_CHECKING:
    from app.models.account import Account


class Goal(Base, TimestampMixin):
    """A savings goal.

    ``current_amount`` is the manually tracked progress. When ``account_id``
    is set the balance can also be derived from that savings account, which
    gives later phases both a manual and an account-backed model.
    """

    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    target_amount: Mapped[MoneyAmount] = mapped_column()
    current_amount: Mapped[MoneyAmount] = mapped_column(default=0.0, server_default="0")
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    account: Mapped[Account | None] = relationship("Account", lazy="selectin")
