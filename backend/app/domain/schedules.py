"""Pure schedule arithmetic for recurring transactions.

No ORM or FastAPI imports: functions operate on plain ``date`` objects so
they are trivially unit testable and shared by the recurring service and
later forecast phases.

Month arithmetic clamps to the target month's last day, so a monthly
occurrence on Jan 31 rolls to Feb 28/29 instead of overflowing into March.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

from app.domain.errors import ValidationError

HEADLESS_FREQUENCIES = {"daily", "weekly", "biweekly"}


def months_shift(anchor: date, months: int) -> date:
    """Step ``anchor`` by whole months, clamping to the target month's end."""
    total = anchor.year * 12 + (anchor.month - 1) + months
    year, zero_indexed = divmod(total, 12)
    target_month = zero_indexed + 1
    last_day = monthrange(year, target_month)[1]
    return date(year, target_month, min(anchor.day, last_day))


def next_occurrence(frequency: str, anchor: date) -> date:
    """The next scheduling date after ``anchor`` for the given frequency."""
    if frequency == "daily":
        return anchor + timedelta(days=1)
    if frequency == "weekly":
        return anchor + timedelta(days=7)
    if frequency == "biweekly":
        return anchor + timedelta(days=14)
    if frequency == "monthly":
        return months_shift(anchor, 1)
    if frequency == "quarterly":
        return months_shift(anchor, 3)
    if frequency == "yearly":
        return months_shift(anchor, 12)
    if frequency == "custom":
        raise ValidationError("custom frequency requires manual scheduling")
    raise ValidationError(f"Unknown frequency '{frequency}'")


def previous_occurrence(frequency: str, anchor: date) -> date:
    """The scheduling date before ``anchor`` (mirror of :func:`next_occurrence`)."""
    if frequency == "daily":
        return anchor - timedelta(days=1)
    if frequency == "weekly":
        return anchor - timedelta(days=7)
    if frequency == "biweekly":
        return anchor - timedelta(days=14)
    if frequency == "monthly":
        return months_shift(anchor, -1)
    if frequency == "quarterly":
        return months_shift(anchor, -3)
    if frequency == "yearly":
        return months_shift(anchor, -12)
    if frequency == "custom":
        raise ValidationError("custom frequency requires manual scheduling")
    raise ValidationError(f"Unknown frequency '{frequency}'")


def occurrences(frequency: str, start: date, through: date) -> list[date]:
    """Every occurrence from ``start`` through ``through`` (inclusive).

    ``start`` itself is included; stepping stops as soon as the next date
    would pass ``through``.
    """
    dates: list[date] = []
    current = start
    while current <= through:
        dates.append(current)
        current = next_occurrence(frequency, current)
    return dates