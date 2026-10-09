"""Domain layer tests (pure functions, no database)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.domain.calculations import (
    AccountBalance,
    income_expense_totals,
    money,
    net_worth,
    percent_change,
    safe_to_spend,
    total,
)
from app.domain.periods import (
    next_period_start,
    period_end,
    period_start,
    previous_period_start,
)


def test_period_start_with_month_start_day_1() -> None:
    assert period_start(date(2026, 10, 17), 1) == date(2026, 10, 1)
    assert period_end(date(2026, 10, 17), 1) == date(2026, 10, 31)


def test_period_start_with_custom_month_start_day() -> None:
    # Periods run from the 15th to the 14th of the following month.
    assert period_start(date(2026, 10, 20), 15) == date(2026, 10, 15)
    assert period_start(date(2026, 10, 10), 15) == date(2026, 9, 15)
    assert period_end(date(2026, 10, 10), 15) == date(2026, 10, 14)


def test_month_start_day_is_clamped() -> None:
    assert period_start(date(2026, 10, 10), 40) == period_start(date(2026, 10, 10), 28)
    assert period_start(date(2026, 10, 10), 0) == period_start(date(2026, 10, 10), 1)


def test_period_neighbours() -> None:
    assert previous_period_start(date(2026, 10, 17), 1) == date(2026, 9, 1)
    assert next_period_start(date(2026, 10, 17), 1) == date(2026, 11, 1)
    # day 15 periods run 15th..14th: Jan 5 sits in Dec 15..Jan 14, so the
    # previous period is Nov 15..Dec 14 (not the current period's start).
    assert previous_period_start(date(2026, 1, 5), 15) == date(2025, 11, 15)
    assert next_period_start(date(2026, 1, 5), 15) == date(2026, 1, 15)


def test_totals() -> None:
    assert total([10, "20.5", Decimal("0.25")]) == Decimal("30.75")
    assert income_expense_totals(
        [("income", 100), ("expense", 40), ("transfer", 50)]
    ) == {"income": Decimal("100"), "expense": Decimal("40"), "net": Decimal("60")}


def test_net_worth_counts_liabilities_as_debt() -> None:
    balances = [
        AccountBalance(1, Decimal("1000")),
        AccountBalance(2, Decimal("250"), is_liability=True),
    ]
    assert net_worth(balances) == Decimal("750")


def test_safe_to_spend_is_never_negative() -> None:
    assert safe_to_spend(money(500), committed=money(150), buffer=money(50)) == Decimal("300")
    assert safe_to_spend(money(100), committed=money(300)) == Decimal("0")


def test_percent_change() -> None:
    assert percent_change(Decimal("150"), Decimal("100")) == Decimal("0.5")
    assert percent_change(Decimal("50"), Decimal("100")) == Decimal("-0.5")
    assert percent_change(Decimal("0"), Decimal("0")) == Decimal("0")
    # No meaningful baseline: going 0 -> anything is not reported as a %.
    assert percent_change(Decimal("500"), Decimal("0")) is None
    assert percent_change(Decimal("100"), Decimal("0")) is None
