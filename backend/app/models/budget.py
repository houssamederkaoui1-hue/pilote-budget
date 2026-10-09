"""Monthly budgets: allocation targets plus per-category plans.

Two levels coexist for the same period:

- a monthly **allocation** (income, needs, wants, savings, other) stored in
  :class:`BudgetAllocation` and
- per-category **budgets** stored in :class:`Budget`.

``month`` stores the *first day of the budget period*, aligned with the
profile's ``month_start_day`` (see ``app.domain.periods``).
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, MoneyAmount, TimestampMixin

if TYPE_CHECKING:
    from app.models.category import Category


class BudgetAllocation(Base, TimestampMixin):
    """Monthly allocation: income, needs, wants, savings and other buckets.

    One row per budget period (``month`` is the period start date).
    """

    __tablename__ = "budget_allocations"

    id: Mapped[int] = mapped_column(primary_key=True)
    month: Mapped[date] = mapped_column(Date, nullable=False, unique=True, index=True)
    income_amount: Mapped[MoneyAmount] = mapped_column(default=0.0, server_default="0")
    needs_amount: Mapped[MoneyAmount] = mapped_column(default=0.0, server_default="0")
    wants_amount: Mapped[MoneyAmount] = mapped_column(default=0.0, server_default="0")
    savings_amount: Mapped[MoneyAmount] = mapped_column(default=0.0, server_default="0")
    other_amount: Mapped[MoneyAmount] = mapped_column(default=0.0, server_default="0")


class Budget(Base, TimestampMixin):
    """Planned amount for a category in a budget period.

    ``month`` stores the *first day of the budget period*, aligned with the
    profile's ``month_start_day`` (see ``app.domain.periods``).
    """

    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint("month", "category_id", name="month_category"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    month: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    planned_amount: Mapped[MoneyAmount] = mapped_column(default=0.0, server_default="0")
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)

    category: Mapped[Category] = relationship("Category", lazy="selectin")
