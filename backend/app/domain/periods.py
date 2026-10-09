"""Month/period arithmetic driven by the user's month-start configuration."""

from __future__ import annotations

from datetime import date, timedelta

MIN_MONTH_START_DAY = 1
MAX_MONTH_START_DAY = 28


def clamp_month_start_day(day: int) -> int:
    return max(MIN_MONTH_START_DAY, min(MAX_MONTH_START_DAY, int(day)))


def period_start(anchor: date, month_start_day: int = 1) -> date:
    """First day of the budget period that contains ``anchor``.

    The period runs from ``month_start_day`` to the day before the next
    month's start (e.g. day 15 -> periods start on the 15th of each month).
    """
    day = clamp_month_start_day(month_start_day)
    if anchor.day >= day:
        return anchor.replace(day=day)
    previous_month = (anchor.replace(day=1) - timedelta(days=1)).replace(day=day)
    return previous_month


def period_end(anchor: date, month_start_day: int = 1) -> date:
    """Last day (inclusive) of the budget period that contains ``anchor``."""
    start = period_start(anchor, month_start_day)
    next_month = (start.replace(day=1) + timedelta(days=32)).replace(day=1)
    following_start = next_month.replace(day=clamp_month_start_day(month_start_day))
    return following_start - timedelta(days=1)


def previous_period_start(anchor: date, month_start_day: int = 1) -> date:
    """First day of the period *before* the one containing ``anchor``.

    Implemented as ``period_start`` of the day before the current period
    starts, so custom month-start days (e.g. 15 -> periods run 15th..14th)
    resolve to the true previous period rather than the current one.
    """
    start = period_start(anchor, month_start_day)
    return period_start(start - timedelta(days=1), month_start_day)


def next_period_start(anchor: date, month_start_day: int = 1) -> date:
    start = period_start(anchor, month_start_day)
    day = clamp_month_start_day(month_start_day)
    return (start.replace(day=1) + timedelta(days=32)).replace(day=day)
