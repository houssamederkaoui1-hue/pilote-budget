"""Pure analytics / forecasting math (framework independent).

All helpers operate on plain values so they can be unit tested without a
database and be reused by services, API responses and the testing layer.
Nothing here knows about SQLAlchemy, FastAPI or the frontend.
"""

from __future__ import annotations

from datetime import date

from app.domain.enums import AccountType

# Account types that represent money the user holds (positive balances).
ASSET_TYPES = {
    AccountType.BANK,
    AccountType.CHECKING,
    AccountType.SAVINGS,
    AccountType.CASH,
    AccountType.DEBIT_CARD,
    AccountType.INVESTMENT,
    AccountType.OTHER,
}

# Account types that represent money owed (balances are stored negative).
LIABILITY_TYPES = {AccountType.CREDIT_CARD, AccountType.LOAN}


def is_liability_type(account_type: AccountType | str) -> bool:
    """True when an account type represents money owed."""
    if not isinstance(account_type, AccountType):
        account_type = AccountType(account_type)
    return account_type in LIABILITY_TYPES


def days_in_period(start: date, end: date) -> int:
    """Number of calendar days in an inclusive ``[start, end]`` window."""
    return (end - start).days + 1


def days_elapsed(start: date, today: date) -> int:
    """Whole elapsed days of a period through ``today`` (inclusive).

    Returns 0 when ``today`` predates the period, so projections can signal
    "nothing to extrapolate from yet".
    """
    if today < start:
        return 0
    return (today - start).days + 1


def straight_line_projection(actual: float, elapsed: int, total: int) -> float | None:
    """Conservative end-of-period estimate from the running pace.

    ``actual / elapsed * total`` assumes the pace seen so far continues. It
    returns ``None`` when there is no elapsed time (first day of a period),
    because extrapolating from zero observations would be fabricated.
    """
    if elapsed <= 0 or total <= 0:
        return None
    return round(float(actual or 0.0) / elapsed * total, 2)


def savings_rate(net: float, income: float) -> float | None:
    """Savings (net of expenses) as a percentage of income.

    ``None`` when there is no income: dividing by zero would be meaningless,
    so callers present an "insufficient data" state instead of a number.
    """
    if income is None or income <= 0:
        return None
    return round(float(net) / float(income) * 100, 1)


def share_of(amount: float, total: float) -> float | None:
    """``amount`` as a percentage of ``total`` (``None`` when no total)."""
    if total is None or total <= 0:
        return None
    return round(float(amount) / float(total) * 100, 1)


def trend_from(change_pct: float | None, threshold: float = 1.0) -> str:
    """Classify a signed percentage change into up / down / flat / none."""
    if change_pct is None:
        return "none"
    if abs(change_pct) < threshold:
        return "flat"
    return "up" if change_pct > 0 else "down"