"""Basic debt tracking and roll-ups.

No payoff algorithm here yet (that is a later phase): the service stores the
tracked balances and reports totals + upcoming due dates for the active
debts.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.errors import NotFoundError, ValidationError
from app.models.debt import Debt
from app.services.validators import validate_account, validate_date, validate_notes


def _coerce(value, label: str) -> float:
    try:
        amount = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{label.title()} must be a number") from exc
    if amount < 0:
        raise ValidationError(f"{label.title()} cannot be negative")
    return amount


def _serialize(debt: Debt) -> dict:
    return {
        "id": debt.id,
        "name": debt.name,
        "creditor": debt.creditor,
        "original_amount": round(float(debt.original_amount), 2),
        "remaining_amount": round(float(debt.remaining_amount), 2),
        "interest_rate": float(debt.interest_rate) if debt.interest_rate is not None else None,
        "minimum_payment": round(float(debt.minimum_payment), 2)
        if debt.minimum_payment is not None
        else None,
        "due_date": debt.due_date,
        "account_id": debt.account_id,
        "account_name": debt.account.name if debt.account else None,
        "active": debt.active,
        "notes": debt.notes,
        "created_at": debt.created_at,
        "updated_at": debt.updated_at,
    }


class DebtService:
    def __init__(self, session: Session):
        self.session = session

    # -- reads ------------------------------------------------------------

    def list(self, include_inactive: bool = True) -> list[dict]:
        stmt = select(Debt)
        if not include_inactive:
            stmt = stmt.where(Debt.active.is_(True))
        rows = self.session.scalars(
            stmt.order_by(Debt.active.desc(), Debt.due_date.nullslast(), Debt.name)
        ).all()
        return [_serialize(debt) for debt in rows]

    def get(self, debt_id: int) -> dict:
        return _serialize(self._must_get(debt_id))

    def totals(self, today: date | None = None) -> dict:
        """Aggregate roll-ups for active debts + the next five due dates."""
        today = today or date.today()
        debts = self.session.scalars(
            select(Debt).where(Debt.active.is_(True)).order_by(Debt.name)
        ).all()

        total_original = round(sum(d.original_amount for d in debts), 2)
        total_remaining = round(sum(d.remaining_amount for d in debts), 2)
        total_minimum = round(
            sum(d.minimum_payment for d in debts if d.minimum_payment is not None), 2
        )

        upcoming = [
            d
            for d in debts
            if d.due_date is not None and d.due_date >= today
        ]
        upcoming.sort(key=lambda debt: debt.due_date)
        upcoming_due_dates = [
            {
                "debt_id": debt.id,
                "name": debt.name,
                "due_date": debt.due_date,
                "remaining_amount": round(float(debt.remaining_amount), 2),
                "minimum_payment": round(float(debt.minimum_payment), 2)
                if debt.minimum_payment is not None
                else None,
            }
            for debt in upcoming[:5]
        ]

        return {
            "total_original": total_original,
            "total_remaining": total_remaining,
            "total_minimum_payment": total_minimum,
            "active_debt_count": len(debts),
            "upcoming_due_dates": upcoming_due_dates,
        }

    # -- writes -----------------------------------------------------------

    def create(
        self,
        *,
        name: str,
        original_amount: float,
        remaining_amount: float | None = None,
        interest_rate: float | None = None,
        minimum_payment: float | None = None,
        due_date: date | None = None,
        account_id: int | None = None,
        notes: str | None = None,
        active: bool = True,
        creditor: str | None = None,
    ) -> dict:
        cleaned_name = (name or "").strip()
        if not cleaned_name:
            raise ValidationError("Debt name is required")
        if len(cleaned_name) > 120:
            raise ValidationError("Debt name must be 120 characters or fewer")

        original = _coerce(original_amount, "original amount")
        remaining = (
            _coerce(remaining_amount, "remaining amount")
            if remaining_amount is not None
            else original
        )
        if remaining > original:
            raise ValidationError("Remaining amount cannot exceed the original amount")
        rate = _coerce(interest_rate, "interest rate") if interest_rate is not None else None
        minimum = (
            _coerce(minimum_payment, "minimum payment") if minimum_payment is not None else None
        )

        if account_id is not None:
            validate_account(self.session, account_id)

        debt = Debt(
            name=cleaned_name,
            creditor=(creditor or "").strip() or None,
            original_amount=round(original, 2),
            remaining_amount=round(remaining, 2),
            interest_rate=round(rate, 3) if rate is not None else None,
            minimum_payment=round(minimum, 2) if minimum is not None else None,
            due_date=validate_date(due_date) if due_date else None,
            account_id=account_id,
            notes=validate_notes(notes),
            active=active,
        )
        self.session.add(debt)
        self.session.flush()
        return _serialize(debt)

    def update(self, debt_id: int, **fields) -> dict:
        debt = self._must_get(debt_id)
        if "name" in fields and fields["name"] is not None:
            cleaned = (fields["name"] or "").strip()
            if not cleaned:
                raise ValidationError("Debt name is required")
            debt.name = cleaned
        if "creditor" in fields:
            debt.creditor = (fields["creditor"] or "").strip() or None
        if "original_amount" in fields and fields["original_amount"] is not None:
            debt.original_amount = round(_coerce(fields["original_amount"], "original amount"), 2)
            if debt.remaining_amount > debt.original_amount:
                raise ValidationError("Remaining amount cannot exceed the original amount")
        if "remaining_amount" in fields and fields["remaining_amount"] is not None:
            remaining = round(_coerce(fields["remaining_amount"], "remaining amount"), 2)
            if remaining > debt.original_amount:
                raise ValidationError("Remaining amount cannot exceed the original amount")
            debt.remaining_amount = remaining
        if "interest_rate" in fields:
            debt.interest_rate = (
                round(_coerce(fields["interest_rate"], "interest rate"), 3)
                if fields["interest_rate"] is not None
                else None
            )
        if "minimum_payment" in fields:
            debt.minimum_payment = (
                round(_coerce(fields["minimum_payment"], "minimum payment"), 2)
                if fields["minimum_payment"] is not None
                else None
            )
        if "due_date" in fields:
            debt.due_date = validate_date(fields["due_date"]) if fields["due_date"] else None
        if "account_id" in fields:
            if fields["account_id"] is not None:
                validate_account(self.session, fields["account_id"])
            debt.account_id = fields["account_id"]
        if "notes" in fields:
            debt.notes = validate_notes(fields["notes"])
        if "active" in fields and fields["active"] is not None:
            debt.active = bool(fields["active"])
        self.session.flush()
        return _serialize(debt)

    def delete(self, debt_id: int) -> None:
        self.session.delete(self._must_get(debt_id))
        self.session.flush()

    def _must_get(self, debt_id: int) -> Debt:
        debt = self.session.get(Debt, debt_id)
        if debt is None:
            raise NotFoundError(f"Debt {debt_id} not found")
        return debt