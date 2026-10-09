"""Recurring transaction templates.

Templates never post by themselves. The only two explicit, testable ways the
schedule moves forward are:

- :meth:`record` — materializes a ledger transaction at the due date, then
  advances ``next_occurrence`` by one frequency step from that date;
- :meth:`advance` — skips the due date by stepping ``next_occurrence`` once.

``upcoming`` is a pure projection: it turns ``next_occurrence`` into a list of
due dates through the horizon without creating or mutating anything. An
overdue ``next_occurrence`` is reported once with ``overdue: true`` and not
extrapolated, so a single missed obligation does not bank a run of copies.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import RecurrenceFrequency, TransactionType
from app.domain.errors import NotFoundError, ValidationError
from app.domain.schedules import (
    next_occurrence as step_next,
    occurrences,
    previous_occurrence as step_back,
)
from app.models.recurring import RecurringTransaction
from app.services.transaction_service import TransactionService
from app.services.validators import (
    validate_account,
    validate_amount,
    validate_category,
    validate_date,
    validate_description,
    validate_enum,
    validate_notes,
)

# Frequencies the scheduler can project; anything else requires manual work.
PLANNED_FREQUENCIES = {
    "daily",
    "weekly",
    "biweekly",
    "monthly",
    "quarterly",
    "yearly",
}


def _enum_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _serialize(template: RecurringTransaction) -> dict:
    return {
        "id": template.id,
        "account_id": template.account_id,
        "account_name": template.account.name if template.account else None,
        "category_id": template.category_id,
        "category_name": template.category.name if template.category else None,
        "type": _enum_value(template.type),
        "amount": template.amount,
        "frequency": _enum_value(template.frequency),
        "next_occurrence": template.next_occurrence,
        "end_date": template.end_date,
        "description": template.description,
        "notes": template.notes,
        "active": template.active,
        "created_at": template.created_at,
        "updated_at": template.updated_at,
    }


class RecurringService:
    def __init__(self, session: Session):
        self.session = session

    # -- reads ------------------------------------------------------------

    def list(self, include_inactive: bool = True) -> list[dict]:
        stmt = select(RecurringTransaction)
        if not include_inactive:
            stmt = stmt.where(RecurringTransaction.active.is_(True))
        rows = self.session.scalars(
            stmt.order_by(
                RecurringTransaction.active.desc(),
                RecurringTransaction.next_occurrence,
            )
        ).all()
        return [_serialize(template) for template in rows]

    def get(self, recurring_id: int) -> dict:
        return _serialize(self._must_get(recurring_id))

    def upcoming(self, today: date, days: int = 30) -> dict:
        """Projection of the next ``days`` days (no ledgers writes)."""
        today = today or date.today()
        days = max(1, min(int(days), 365))
        horizon = today + timedelta(days=days)

        templates = self.session.scalars(
            select(RecurringTransaction).where(
                RecurringTransaction.active.is_(True),
                RecurringTransaction.next_occurrence <= horizon,
            )
        ).all()

        occurrences_list: list[dict] = []
        for template in templates:
            if _enum_value(template.frequency) == "custom":
                # Manual schedule: the stored next_occurrence is the obligation.
                due_dates = [template.next_occurrence]
            elif template.next_occurrence < today:
                due_dates = [template.next_occurrence]
            else:
                due_dates = occurrences(
                    _enum_value(template.frequency), template.next_occurrence, horizon
                )
            for due in due_dates:
                if template.end_date is not None and due > template.end_date:
                    continue
                occurrences_list.append(
                    {
                        "recurring_id": template.id,
                        "due_date": due,
                        "overdue": due < today,
                        "type": _enum_value(template.type),
                        "amount": template.amount,
                        "frequency": _enum_value(template.frequency),
                        "description": template.description,
                        "account_id": template.account_id,
                        "account_name": template.account.name if template.account else None,
                        "category_id": template.category_id,
                        "category_name": template.category.name if template.category else None,
                        "end_date": template.end_date,
                    }
                )

        occurrences_list.sort(key=lambda item: item["due_date"])
        return {
            "as_of": today,
            "horizon_days": days,
            "horizon_end": horizon,
            "occurrences": occurrences_list,
        }

    # -- writes -----------------------------------------------------------

    def create(
        self,
        *,
        account_id: int,
        type: str | TransactionType,
        amount: float,
        frequency: str | RecurrenceFrequency,
        next_occurrence: date | None = None,
        end_date: date | None = None,
        category_id: int | None = None,
        description: str = "",
        notes: str | None = None,
        active: bool = True,
    ) -> dict:
        account = validate_account(self.session, account_id)
        recurring_type = validate_enum(type, TransactionType, "type")
        if recurring_type == TransactionType.TRANSFER:
            raise ValidationError(
                "Scheduled transfers are not supported yet; use income or expense"
            )
        frequency_value = validate_enum(
            frequency, RecurrenceFrequency, "frequency"
        ).value
        if frequency_value == "custom":
            raise ValidationError(
                "Custom frequencies require manual scheduling; pick daily, weekly, "
                "biweekly, monthly, quarterly or yearly"
            )
        if frequency_value not in PLANNED_FREQUENCIES:
            raise ValidationError(f"Unknown frequency '{frequency_value}'")

        if category_id is not None:
            validate_category(
                self.session, category_id, expected_type=recurring_type.value
            )

        due = validate_date(next_occurrence) if next_occurrence else date.today()
        end = validate_date(end_date) if end_date else None
        if end is not None and end < due:
            raise ValidationError("end_date must be on or after next_occurrence")

        template = RecurringTransaction(
            account_id=account.id,
            category_id=category_id,
            type=recurring_type,
            amount=validate_amount(amount),
            frequency=frequency_value,
            next_occurrence=due,
            end_date=end,
            description=validate_description(description),
            notes=validate_notes(notes),
            active=active,
        )
        self.session.add(template)
        self.session.flush()
        return _serialize(template)

    def update(self, recurring_id: int, **fields) -> dict:
        template = self._must_get(recurring_id)
        if "account_id" in fields and fields["account_id"] is not None:
            account = validate_account(self.session, fields["account_id"])
            template.account_id = account.id
        if "type" in fields and fields["type"] is not None:
            value = validate_enum(fields["type"], TransactionType, "type")
            if value == TransactionType.TRANSFER:
                raise ValidationError("Scheduled transfers are not supported yet")
            template.type = value
        if "amount" in fields and fields["amount"] is not None:
            template.amount = validate_amount(fields["amount"])
        if "frequency" in fields and fields["frequency"] is not None:
            value = validate_enum(fields["frequency"], RecurrenceFrequency, "frequency")
            if value.value not in PLANNED_FREQUENCIES:
                raise ValidationError(
                    f"Frequency '{value.value}' cannot be scheduled; use daily, "
                    "weekly, biweekly, monthly, quarterly or yearly"
                )
            template.frequency = value
        if "next_occurrence" in fields and fields["next_occurrence"] is not None:
            template.next_occurrence = validate_date(fields["next_occurrence"])
        if "end_date" in fields:
            end = validate_date(fields["end_date"]) if fields["end_date"] else None
            if end is not None and end < template.next_occurrence:
                raise ValidationError("end_date must be on or after next_occurrence")
            template.end_date = end
        if "category_id" in fields:
            if fields["category_id"] is not None:
                category = validate_category(
                    self.session, fields["category_id"], expected_type=_enum_value(template.type)
                )
                template.category_id = category.id
            else:
                template.category_id = None
        if "description" in fields:
            template.description = validate_description(fields["description"])
        if "notes" in fields:
            template.notes = validate_notes(fields["notes"])
        if "active" in fields and fields["active"] is not None:
            template.active = bool(fields["active"])
        self.session.flush()
        return _serialize(template)

    def record(
        self, recurring_id: int, at_date: date | None = None
    ) -> dict:
        """Materialize the due occurrence and advance the schedule.

        Rule: a ledger transaction is created at ``at_date`` (defaults to the
        stored ``next_occurrence``). The next occurrence then steps forward
        from that date. When the step passes ``end_date`` the template is
        deactivated (schedule complete).

        An explicit ``at_date`` is only accepted inside the current due window
        — strictly after the previously scheduled occurrence and no later than
        the due occurrence (or today when it is overdue). This keeps recording
        idempotent (the same due occurrence cannot be posted twice) and stops
        arbitrary far-future dated ledger rows, while still allowing the
        already-scheduled next occurrence to be recorded in advance.
        Because the due date is advanced on every record, the
        ``next_occurrence`` passed along is always acceptable without an
        explicit date.
        """
        template = self._must_get(recurring_id)
        if not template.active:
            raise ValidationError("Inactive recurring template cannot be recorded")

        if at_date is None:
            due = template.next_occurrence
        else:
            due = validate_date(at_date)
            window_start = step_back(
                _enum_value(template.frequency), template.next_occurrence
            )
            window_end = max(template.next_occurrence, date.today())
            if not (window_start < due <= window_end):
                raise ValidationError(
                    "That date is outside the current due window; record the "
                    f"occurrence between {window_start.isoformat()} and {window_end.isoformat()}"
                )
            if (
                due != template.next_occurrence
                and step_back(
                    _enum_value(template.frequency), step_next(_enum_value(template.frequency), due)
                )
                != due
            ):
                raise ValidationError(
                    "That date is not an occurrence in this schedule; use the "
                    "scheduled date or a stable reschedule date"
                )

        TransactionService(self.session).create(
            type=_enum_value(template.type),
            amount=template.amount,
            account_id=template.account_id,
            category_id=template.category_id,
            date=due,
            description=template.description,
            notes=template.notes,
        )

        next_due = step_next(_enum_value(template.frequency), due)
        inactivated = False
        if template.end_date is not None and next_due > template.end_date:
            inactivated = True
            template.active = False
        template.next_occurrence = next_due
        self.session.flush()

        return {
            "recurring_id": template.id,
            "date": due,
            "next_occurrence": template.next_occurrence,
            "deactivated": inactivated,
            "template": _serialize(template),
        }

    def advance(self, recurring_id: int) -> dict:
        """Skip the stored occurrence without posting a transaction."""
        template = self._must_get(recurring_id)
        if not template.active:
            raise ValidationError("Inactive recurring template cannot be advanced")
        next_due = step_next(_enum_value(template.frequency), template.next_occurrence)
        inactivated = False
        if template.end_date is not None and next_due > template.end_date:
            inactivated = True
            template.active = False
        template.next_occurrence = next_due
        self.session.flush()
        return {
            "recurring_id": template.id,
            "next_occurrence": template.next_occurrence,
            "deactivated": inactivated,
            "template": _serialize(template),
        }

    def delete(self, recurring_id: int) -> None:
        self.session.delete(self._must_get(recurring_id))
        self.session.flush()

    def _must_get(self, recurring_id: int) -> RecurringTransaction:
        template = self.session.get(RecurringTransaction, recurring_id)
        if template is None:
            raise NotFoundError(f"Recurring template {recurring_id} not found")
        return template