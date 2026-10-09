"""Budget engine: planned vs actual vs remaining vs utilisation.

The API is the only consumer of these numbers when building the budget
dashboard; frontend components never recompute them indepentially.

Planned values come from the per-period allocation row and per-category
budget rows. Actual spending is scraped from the transaction ledger (posted
statuses only, expense only), so transfers and income can never leak in.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.domain.budget import utilization
from app.domain.enums import TransactionStatus, TransactionType
from app.domain.errors import NotFoundError, ValidationError
from app.domain.periods import period_end, period_start
from app.models.budget import Budget, BudgetAllocation
from app.models.category import Category
from app.models.transaction import Transaction
from app.services.profile_service import ProfileService

POSTED = (
    TransactionStatus.PENDING,
    TransactionStatus.CLEARED,
    TransactionStatus.RECONCILED,
)

ALLOCATION_FIELDS = ("needs", "wants", "savings", "other")


def _round(value: float | None) -> float | None:
    return None if value is None else round(float(value), 2)


def _round0(value: float | None) -> float:
    return round(float(value or 0.0), 2)


class BudgetService:
    def __init__(self, session: Session):
        self.session = session

    # -- period helpers ----------------------------------------------------

    def month_start_day(self) -> int:
        return ProfileService(self.session).get().month_start_day

    def period_bounds(self, anchor: date) -> tuple[date, date]:
        start = period_start(anchor, self.month_start_day())
        return start, period_end(anchor, self.month_start_day())

    # -- ledger reads --------------------------------------------------------

    def _expense_by_category(self, start: date, end: date) -> dict[int, float]:
        rows = self.session.execute(
            select(
                Transaction.category_id,
                func.sum(Transaction.amount),
            )
            .where(
                Transaction.type == TransactionType.EXPENSE,
                Transaction.status.in_(POSTED),
                Transaction.date >= start,
                Transaction.date <= end,
                Transaction.category_id.is_not(None),
            )
            .group_by(Transaction.category_id)
        ).all()
        return {category_id: _round0(total) for category_id, total in rows}

    def _total_expense(self, start: date, end: date) -> float:
        total = self.session.execute(
            select(func.sum(Transaction.amount)).where(
                Transaction.type == TransactionType.EXPENSE,
                Transaction.status.in_(POSTED),
                Transaction.date >= start,
                Transaction.date <= end,
            )
        ).scalar()
        return _round0(total)

    # -- the engine --------------------------------------------------------

    def summary(self, anchor: date) -> dict:
        """Full budget view for the period containing ``anchor``.

        Never raises when the month has no plan: a zeroed allocation and the
        active categories with any planned amount or spending are returned.
        """
        start, end = self.period_bounds(anchor)
        allocation = self.session.execute(
            select(BudgetAllocation).where(BudgetAllocation.month == start)
        ).scalar_one_or_none()
        plan = list(self.session.scalars(select(Budget).where(Budget.month == start)))
        spend = self._expense_by_category(start, end)
        total_actual = self._total_expense(start, end)

        planned_by_category = {item.category_id: _round0(item.planned_amount) for item in plan}
        notes_by_category = {item.category_id: item.notes for item in plan}

        # Active expense categories are the universe a category budget can
        # target; each row carries its (planned, actual, remaining, pct, over).
        categories = self.session.scalars(
            select(Category)
            .where(Category.active.is_(True), Category.type == "expense")
            .order_by(Category.name)
        ).all()

        items: list[dict] = []
        for category in categories:
            planned = planned_by_category.get(category.id, 0.0)
            actual = spend.get(category.id, 0.0)
            if planned == 0 and actual == 0:
                continue
            pct, over, status = utilization(actual, planned)
            items.append(
                {
                    "category_id": category.id,
                    "category_name": category.name,
                    "planned_amount": planned,
                    "actual_amount": _round0(actual),
                    "remaining_amount": _round0(planned - actual),
                    "pct_used": _round(pct),
                    "over_budget": over,
                    "status": status,
                    "notes": notes_by_category.get(category.id),
                }
            )

        total_planned = _round0(sum(item["planned_amount"] for item in items))
        # ``total_actual`` is the full posted-expense figure for the period
        # (computed above), which includes spending that is uncategorized or on
        # archived categories — otherwise "Am I over budget?" would understate it.
        total_pct, total_over, _ = utilization(total_actual, total_planned)

        allocation_values = {
            f"{name}_amount": _round0(getattr(allocation, f"{name}_amount"))
            if allocation is not None
            else 0.0
            for name in ALLOCATION_FIELDS
        }
        alloc_planned = _round0(sum(allocation_values.values()))
        alloc_pct, alloc_over, _ = utilization(total_actual, alloc_planned)

        allocation_stats = {
            "income_amount": _round0(allocation.income_amount) if allocation else 0.0,
            **allocation_values,
            "planned_total": alloc_planned,
            "actual_total": total_actual,
            "remaining_total": _round0(alloc_planned - total_actual),
            "pct_used": _round(alloc_pct),
            "over_budget": alloc_over,
            "has_allocation": allocation is not None,
        }

        return {
            "period_start": start,
            "period_end": end,
            "month_start_day": self.month_start_day(),
            "allocation": allocation_stats,
            "items": items,
            "totals": {
                "planned": total_planned,
                "actual": total_actual,
                "remaining": _round0(total_planned - total_actual),
                "pct_used": _round(total_pct),
                "over_budget": total_over,
            },
            "approaching": [
                item["category_id"] for item in items if item["status"] == "approaching"
            ],
            "exceeding": [
                item["category_id"] for item in items if item["status"] == "over"
            ],
        }

    # -- writes -------------------------------------------------------------

    def put(
        self,
        anchor: date,
        *,
        allocation: dict | None = None,
        items: list[dict] | None = None,
    ) -> dict:
        """Replace the month's plan (allocation + category items) wholesale."""
        start, _end = self.period_bounds(anchor)

        self.session.execute(delete(BudgetAllocation).where(BudgetAllocation.month == start))
        self.session.execute(delete(Budget).where(Budget.month == start))

        if allocation:
            amounts: dict[str, float] = {}
            for name in ("income", *ALLOCATION_FIELDS):
                raw = allocation.get(name, None) if isinstance(allocation, dict) else getattr(allocation, name, None)
                amounts[name] = self._coerce_planned(
                    raw if raw is not None else 0.0, name
                )
            if any(amounts[name] != 0.0 for name in ("income", *ALLOCATION_FIELDS)):
                self.session.add(
                    BudgetAllocation(
                        month=start,
                        income_amount=amounts["income"],
                        needs_amount=amounts["needs"],
                        wants_amount=amounts["wants"],
                        savings_amount=amounts["savings"],
                        other_amount=amounts["other"],
                    )
                )

        seen: set[int] = set()
        for entry in items or []:
            category_id = int(entry["category_id"])
            if category_id in seen:
                raise ValidationError(f"Category {category_id} is listed more than once")
            seen.add(category_id)

            category = self.session.get(Category, category_id)
            if category is None:
                raise NotFoundError(f"Category {category_id} not found")
            if not category.active:
                raise ValidationError(f"Category '{category.name}' is archived")
            if category.type.value != "expense":
                raise ValidationError(
                    f"Category '{category.name}' is an income category; only expense "
                    "categories can carry a budget"
                )
            planned = self._coerce_planned(entry.get("planned_amount"), "planned amount")
            notes = (entry.get("notes") or "").strip() or None
            self.session.add(
                Budget(
                    month=start,
                    category_id=category_id,
                    planned_amount=planned,
                    notes=notes,
                )
            )

        self.session.flush()
        return self.summary(start)

    @staticmethod
    def _coerce_planned(value, label: str) -> float:
        try:
            amount = float(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"{label.title()} must be a number") from exc
        if amount < 0:
            raise ValidationError(f"{label.title()} cannot be negative")
        return round(amount, 2)