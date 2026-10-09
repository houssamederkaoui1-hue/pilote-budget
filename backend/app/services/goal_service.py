"""Goal service: progress tracking, pacing and completion estimates.

Computed fields are always derived here (never in frontend components):

- ``progress_pct`` — current / target
- ``remaining`` — target minus current (never negative)
- ``required_monthly_saving`` — the even monthly deposit needed to hit
  ``target_date`` (None when there is no deadline)
- ``monthly_contribution`` — the current contribution rate, estimated from
  the average net savings of the last two completed months
- ``estimated_completion_date`` — when the goal would fund at that rate
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.errors import NotFoundError, ValidationError
from app.domain.goals import (
    estimated_completion,
    progress_percent,
    remaining as remaining_calc,
    required_monthly_saving as required_saving_calc,
)
from app.models.goal import Goal
from app.services.balance_service import BalanceService


def _coerce_non_negative(value, label: str) -> float:
    try:
        amount = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{label.title()} must be a number") from exc
    if amount < 0:
        raise ValidationError(f"{label.title()} cannot be negative")
    return amount


def _decorate_goal(goal: Goal, today: date, contribution_rate: float | None) -> dict:
    current = float(goal.current_amount)
    target = float(goal.target_amount)
    remaining = remaining_calc(target, current)
    required = required_saving_calc(target, current, goal.target_date, today)
    estimated = estimated_completion(remaining, contribution_rate, today)
    return {
        "id": goal.id,
        "name": goal.name,
        "target_amount": round(target, 2),
        "current_amount": round(current, 2),
        "target_date": goal.target_date,
        "account_id": goal.account_id,
        "account_name": goal.account.name if goal.account else None,
        "active": goal.active,
        "notes": goal.notes,
        "created_at": goal.created_at,
        "updated_at": goal.updated_at,
        "progress_pct": progress_percent(current, target),
        "remaining_amount": remaining,
        "required_monthly_saving": required,
        "monthly_contribution": contribution_rate,
        "estimated_completion_date": estimated,
    }


class GoalService:
    def __init__(self, session: Session):
        self.session = session

    # -- reads ------------------------------------------------------------

    def _contribution_rate(self, today: date) -> float | None:
        """Average monthly net saving over the last two completed months."""
        current_month_start = today.replace(day=1)
        last_end = current_month_start - timedelta(days=1)
        last_start = last_end.replace(day=1)
        prior_end = last_start - timedelta(days=1)
        prior_start = prior_end.replace(day=1)

        balances = BalanceService(self.session)
        last_net = balances.summary(last_start, last_end)["net"]
        prior_net = balances.summary(prior_start, prior_end)["net"]
        candidates = [value for value in (last_net, prior_net) if value and value > 0]
        if not candidates:
            return None
        return round(sum(candidates) / len(candidates), 2)

    def list(self, today: date | None = None) -> list[dict]:
        today = today or date.today()
        rate = self._contribution_rate(today)
        goals = self.session.scalars(
            select(Goal).order_by(Goal.active.desc(), Goal.created_at.desc())
        ).all()
        return [_decorate_goal(goal, today, rate) for goal in goals]

    def get(self, goal_id: int, today: date | None = None) -> dict:
        today = today or date.today()
        return _decorate_goal(
            self._must_get(goal_id), today, self._contribution_rate(today)
        )

    # -- writes -----------------------------------------------------------

    def create(
        self,
        *,
        name: str,
        target_amount: float,
        current_amount: float = 0.0,
        target_date: date | None = None,
        account_id: int | None = None,
        notes: str | None = None,
        active: bool = True,
    ) -> dict:
        from app.services.validators import validate_account, validate_date

        cleaned_name = (name or "").strip()
        if not cleaned_name:
            raise ValidationError("Goal name is required")
        if len(cleaned_name) > 120:
            raise ValidationError("Goal name must be 120 characters or fewer")

        target = _coerce_non_negative(target_amount, "target amount")
        if target <= 0:
            raise ValidationError("Target amount must be greater than zero")
        current = _coerce_non_negative(current_amount, "current amount")

        if account_id is not None:
            validate_account(self.session, account_id)

        goal = Goal(
            name=cleaned_name,
            target_amount=round(target, 2),
            current_amount=round(current, 2),
            target_date=validate_date(target_date) if target_date else None,
            account_id=account_id,
            notes=(notes or "").strip() or None,
            active=active,
        )
        self.session.add(goal)
        self.session.flush()
        return self.get(goal.id)

    def update(self, goal_id: int, today: date | None = None, **fields) -> dict:
        from app.services.validators import validate_account, validate_date

        goal = self._must_get(goal_id)
        if "name" in fields and fields["name"] is not None:
            cleaned = (fields["name"] or "").strip()
            if not cleaned:
                raise ValidationError("Goal name is required")
            goal.name = cleaned
        if "target_amount" in fields and fields["target_amount"] is not None:
            amount = _coerce_non_negative(fields["target_amount"], "target amount")
            if amount <= 0:
                raise ValidationError("Target amount must be greater than zero")
            goal.target_amount = round(amount, 2)
        if "current_amount" in fields and fields["current_amount"] is not None:
            goal.current_amount = round(
                _coerce_non_negative(fields["current_amount"], "current amount"), 2
            )
        if "target_date" in fields:
            goal.target_date = (
                validate_date(fields["target_date"]) if fields["target_date"] else None
            )
        if "account_id" in fields:
            if fields["account_id"] is not None:
                validate_account(self.session, fields["account_id"])
            goal.account_id = fields["account_id"]
        if "notes" in fields:
            goal.notes = (fields["notes"] or "").strip() or None
        if "active" in fields and fields["active"] is not None:
            goal.active = bool(fields["active"])
        self.session.flush()
        return self.get(goal.id, today)

    def delete(self, goal_id: int) -> None:
        self.session.delete(self._must_get(goal_id))
        self.session.flush()

    def _must_get(self, goal_id: int):
        goal = self.session.get(Goal, goal_id)
        if goal is None:
            raise NotFoundError(f"Goal {goal_id} not found")
        return goal