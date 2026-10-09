"""Pure analytics + Safe-to-Spend domain tests (no database)."""

from __future__ import annotations

from datetime import date

from app.domain.analytics import (
    days_elapsed,
    days_in_period,
    is_liability_type,
    savings_rate,
    share_of,
    straight_line_projection,
    trend_from,
)
from app.domain.safetospend import calculate as safe_to_spend_formula


def test_days_in_period_is_inclusive():
    assert days_in_period(date(2026, 10, 8), date(2026, 10, 31)) == 24
    assert days_in_period(date(2026, 10, 31), date(2026, 10, 31)) == 1


def test_days_elapsed_includes_today():
    assert days_elapsed(date(2026, 10, 1), date(2026, 10, 8)) == 8
    assert days_elapsed(date(2026, 10, 1), date(2026, 10, 1)) == 1
    assert days_elapsed(date(2026, 10, 15), date(2026, 10, 8)) == 0


def test_leap_year_february_window():
    assert days_in_period(date(2024, 2, 1), date(2024, 2, 29)) == 29
    assert days_elapsed(date(2024, 2, 1), date(2024, 2, 29)) == 29
    # day 28/29 handling: 2023 is not a leap year, so Feb ends on the 28th.
    assert days_in_period(date(2023, 2, 1), date(2023, 2, 28)) == 28


def test_straight_line_projection():
    # 650 spent over 8 days of a 31-day period -> pace keeps holding.
    assert straight_line_projection(650.0, 8, 31) == round(650 / 8 * 31, 2)
    # Zero elapsed days: nothing to extrapolate from -> None (not invented).
    assert straight_line_projection(650.0, 0, 31) is None
    assert straight_line_projection(650.0, 8, 0) is None
    assert straight_line_projection(0.0, 8, 31) == 0.0


def test_leap_year_projection_denominator():
    # Spending 500 in the first 14 days of Feb 2024 (29 days) carries forward.
    expected = round(500 / 14 * 29, 2)
    assert straight_line_projection(500.0, 14, 29) == expected


def test_savings_rate():
    assert savings_rate(2350.0, 3000.0) == round(2350 / 3000 * 100, 1)
    assert savings_rate(50.0, 0.0) is None
    assert savings_rate(-100.0, 1000.0) == -10.0


def test_share_of():
    assert share_of(500.0, 650.0) == round(500 / 650 * 100, 1)
    assert share_of(100.0, 0.0) is None
    assert share_of(0.0, 650.0) == 0.0


def test_trend_from():
    assert trend_from(None) == "none"
    assert trend_from(0.5) == "flat"
    assert trend_from(-0.5) == "flat"
    assert trend_from(20.0) == "up"
    assert trend_from(-20.0) == "down"


def test_liability_account_kinds():
    assert is_liability_type("credit_card") is True
    assert is_liability_type("loan") is True
    assert is_liability_type("checking") is False
    assert is_liability_type("savings") is False


def test_safe_to_spend_formula():
    result = safe_to_spend_formula(
        available=3150.0,
        obligations=400.0,
        planned_savings=600.0,
        reserve=100.0,
        remaining_days=24,
    )
    assert result["committed"] == 1100.0
    assert result["discretionary"] == 2050.0
    assert result["daily"] == round(2050 / 24, 2)
    # The explanation quotes every input so the figure is auditable.
    assert "3150.00" in result["explanation"]
    assert "2050.00" in result["explanation"]
    assert "85.42" in result["explanation"]


def test_safe_to_spend_clamps_at_zero():
    result = safe_to_spend_formula(available=100.0, obligations=300.0, planned_savings=0.0, reserve=0.0, remaining_days=10)
    assert result["discretionary"] == 0.0
    assert result["daily"] == 0.0


def test_safe_to_spend_daily_requires_remaining_days():
    result = safe_to_spend_formula(available=100.0, obligations=0.0, planned_savings=0.0, reserve=0.0, remaining_days=0)
    assert result["discretionary"] == 100.0
    assert result["daily"] is None