"""Pure financial calculations.

All functions operate on plain Python values so they can be unit tested and
reused by services, API responses and (later) the forecasting/analytics layer.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal

Money = Decimal


@dataclass(frozen=True)
class AccountBalance:
    account_id: int
    balance: Money
    is_liability: bool = False


def money(value: float | int | str | Decimal) -> Money:
    """Coerce a value into an exact ``Decimal`` money amount."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def total(values: Iterable[float | int | str | Decimal]) -> Money:
    return sum((money(v) for v in values), Decimal("0"))


def net_worth(balances: Iterable[AccountBalance]) -> Money:
    """Assets minus liabilities (balances are signed as held in the account)."""
    result = Decimal("0")
    for item in balances:
        result += -item.balance if item.is_liability else item.balance
    return result


def income_expense_totals(
    rows: Iterable[tuple[str, float | int | str | Decimal]],
) -> Mapping[str, Money]:
    """Sum ``(kind, amount)`` pairs into ``{"income": X, "expense": Y, "net": Z}``."""
    income = Decimal("0")
    expense = Decimal("0")
    for kind, amount in rows:
        value = money(amount)
        if kind == "income":
            income += value
        elif kind == "expense":
            expense += value
    return {"income": income, "expense": expense, "net": income - expense}


def safe_to_spend(
    available_balance: Money,
    committed: Money = Decimal("0"),
    buffer: Money = Decimal("0"),
) -> Money:
    """Placeholder Safe-to-Spend formula.

    Refinements (recurring bills, goal funding, forecast) arrive in later
    phases; the signature keeps the inputs explicit so it can grow cleanly.
    """
    result = money(available_balance) - money(committed) - money(buffer)
    return max(result, Decimal("0"))


def percent_change(current: Money, previous: Money) -> Decimal | None:
    """Percentage change between two periods, as a decimal fraction.

    Returns ``None`` when there is no meaningful baseline (previous month was
    zero) — reporting "+100%" for going from nothing to something overstates
    the change and misleads the trend and assistant text.
    """
    current = money(current)
    previous = money(previous)
    if previous == 0:
        return Decimal("0") if current == 0 else None
    return (current - previous) / abs(previous)
