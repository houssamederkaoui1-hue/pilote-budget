"""Pure goal math: progress, remaining, pacing and completion dates.

All functions take plain numbers/dates so they can be unit tested without a
database and reused by the goal service, API responses and later funding
logic.
"""

from __future__ import annotations

import math
from datetime import date

from app.domain.schedules import months_shift


def progress_percent(current: float, target: float) -> float:
    """0..100+ completion percentage (may exceed 100 when overfunded)."""
    if target <= 0:
        return 0.0
    return round(float(current) / float(target) * 100, 1)


def remaining(target: float, current: float) -> float:
    return round(max(0.0, float(target) - float(current)), 2)


def months_between(start: date, end: date) -> int:
    """Whole calendar months from ``start`` to ``end`` (>= 0)."""
    diff = (end.year - start.year) * 12 + (end.month - start.month)
    return max(0, diff)


def required_monthly_saving(
    target_amount: float, current_amount: float, target_date: date | None, today: date
) -> float | None:
    """Even monthly deposit needed to hit the target by ``target_date``.

    ``None`` when there is no deadline (the pacing is unknown). When the
    deadline has already passed (or falls this month) the whole remaining
    balance is required now.
    """
    if target_date is None:
        return None
    remaining_amount = remaining(target_amount, current_amount)
    if remaining_amount <= 0:
        return 0.0
    months = max(1, months_between(today, target_date))
    return round(remaining_amount / months, 2)


def estimated_completion(
    remaining_amount: float, monthly_contribution: float | None, today: date
) -> date | None:
    """When the goal would be funded at the current contribution rate.

    ``None`` when there is nothing left to save or no reliable rate.
    """
    if remaining_amount <= 0:
        return today
    if not monthly_contribution or monthly_contribution <= 0:
        return None
    months_needed = math.ceil(remaining_amount / monthly_contribution)
    return months_shift(today, max(1, months_needed))