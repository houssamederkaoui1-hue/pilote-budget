"""Suggestion service: category hints and duplicate detection for Quick Add.

Loads compact aggregates from the ledger (transactions + recurring templates)
and delegates the deterministic ranking to ``app.domain.suggestions``.
Duplicate detection uses an explicit-date window so the user can quickly spot
"did I already log this?" without an exact-match dependency on imports.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.enums import TransactionType
from app.domain.errors import ConflictError
from app.domain.suggestions import normalize_description, rank_suggestions
from app.models.category import Category
from app.models.recurring import RecurringTransaction
from app.models.transaction import Transaction


class SuggestionService:
    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _aggregate(rows) -> tuple[dict, list[dict]]:
        usage: dict[str, list[dict]] = {}
        for desc_norm, category_id, category_name, count in rows:
            if category_id is None:
                continue
            usage.setdefault(desc_norm, []).append(
                {
                    "description": desc_norm,
                    "category_id": category_id,
                    "category_name": category_name,
                    "count": int(count),
                }
            )
        totals: list[dict] = []
        seen: set[tuple[int, str]] = set()
        for desc_norm, category_id, category_name, count in rows:
            key = (category_id, category_name)
            if key in seen:
                continue
            seen.add(key)
            totals.append(
                {
                    "description": desc_norm,
                    "category_id": category_id,
                    "category_name": category_name,
                    "count": int(count),
                }
            )
        return usage, totals

    def suggest_categories(
        self, description: str, type: str | TransactionType, limit: int = 5
    ) -> list[dict]:
        transaction_type = TransactionType(type)
        rows = (
            self.session.execute(
                select(
                    Transaction.description,
                    Transaction.category_id,
                    Category.name.label("category_name"),
                    func.count(Transaction.id),
                )
                .join(Transaction.category)
                .where(Transaction.type == transaction_type)
                .where(Transaction.category_id.is_not(None))
                .group_by(
                    Transaction.description,
                    Transaction.category_id,
                    Category.name,
                )
                .order_by(func.count(Transaction.id).desc())
                .limit(400)
            )
            .all()
        )
        mapped = [
            (normalize_description(desc), category_id, category_name, count)
            for desc, category_id, category_name, count in rows
        ]
        recurring = (
            self.session.execute(
                select(
                    RecurringTransaction.description,
                    RecurringTransaction.category_id,
                    Category.name.label("category_name"),
                    func.count(RecurringTransaction.id),
                )
                .join(RecurringTransaction.category)
                .where(RecurringTransaction.type == transaction_type)
                .where(RecurringTransaction.category_id.is_not(None))
                .where(RecurringTransaction.active.is_(True))
                .group_by(
                    RecurringTransaction.description,
                    RecurringTransaction.category_id,
                    Category.name,
                )
            )
            .all()
        )
        mapped += [
            (normalize_description(desc), category_id, category_name, count + 2)
            for desc, category_id, category_name, count in recurring
        ]
        usage, totals = self._aggregate(mapped)
        self.session.commit()
        return rank_suggestions(description or "", usage, totals, limit=limit)

    def find_duplicates(
        self,
        description: str,
        type: str | TransactionType,
        amount: float,
        on: date | None = None,
        account_id: int | None = None,
        within_days: int = 5,
    ) -> list[dict]:
        """Transactions that look like the same entry already logged."""
        on = on or date.today()
        transaction_type = TransactionType(type)
        start = on - timedelta(days=within_days)
        end = on + timedelta(days=within_days)
        desc_norm = normalize_description(description)

        query = (
            select(Transaction)
            .where(Transaction.type == transaction_type)
            .where(Transaction.date >= start)
            .where(Transaction.date <= end)
        )
        candidates = list(self.session.scalars(query).all())
        matches: list[dict] = []
        for tx in candidates:
            if account_id is not None and tx.account_id != account_id:
                continue
            if desc_norm and normalize_description(tx.description) == desc_norm:
                amount_matches = _amount_tolerance(tx.amount, amount)
                if not amount_matches:
                    continue
                matches.append(
                    {
                        "id": tx.id,
                        "account_id": tx.account_id,
                        "date": tx.date.isoformat(),
                        "amount": float(tx.amount),
                        "description": tx.description,
                        "same_day": tx.date == on,
                        "days_apart": abs((tx.date - on).days),
                    }
                )
        matches.sort(key=lambda row: (not row["same_day"], row["days_apart"]))
        self.session.commit()
        return matches

    def reject_if_duplicate(self, *args, **kwargs) -> None:
        """Raise ConflictError when a same-day, same-amount match exists."""
        if self.find_duplicates(*args, **kwargs):
            raise ConflictError(
                "A matching transaction was already logged for this period. "
                "Use the classify suggestion instead of creating a duplicate."
            )


def _amount_tolerance(left: float, right: float, digits: int = 2) -> bool:
    return abs(round(float(left), digits) - round(float(right), digits)) < 0.005