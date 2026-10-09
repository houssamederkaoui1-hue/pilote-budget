"""Analytics schemas (trends, history, forecasts, health, insights, Safe-to-Spend)."""

from __future__ import annotations

from datetime import date

from app.schemas.base import APIModel


class PeriodWindow(APIModel):
    period_start: date
    period_end: date
    closed: bool


class FlowSummary(APIModel):
    current: float
    previous: float
    change_pct: float | None
    trend: str  # up | down | flat | none


class SavingsSummary(APIModel):
    current: float
    previous: float
    change_pct: float | None
    rate: float | None
    rate_status: str  # positive | neutral | negative | insufficient
    historical_rate: float | None


class CategoryBreakdown(APIModel):
    category_id: int | None
    category_name: str | None
    amount: float
    share_pct: float | None
    change_pct: float | None


class NetWorth(APIModel):
    assets: float
    liabilities: float
    net_worth: float
    net_worth_including_debts: float
    previous: float | None
    change_pct: float | None


class NetWorthHistoryPoint(APIModel):
    period_start: date
    period_end: date
    closed: bool
    assets: float
    liabilities: float
    net_worth: float


class PeriodPoint(APIModel):
    period_start: date
    period_end: date
    closed: bool
    income: float
    expense: float
    net: float
    savings_rate: float | None


class ForecastMetric(APIModel):
    actual: float
    estimated: float | None
    is_estimate: bool


class BalanceForecast(APIModel):
    opening: float
    current: float
    estimated_end: float | None
    is_estimate: bool


class Forecasts(APIModel):
    spending: ForecastMetric
    income: ForecastMetric
    savings: ForecastMetric
    available: BalanceForecast
    note: str


class FinancialHealth(APIModel):
    savings_rate: float | None
    savings_rate_status: str
    budget_pct_used: float | None
    budget_over: bool
    recurring_expense_ratio: float | None
    recurring_expense_ratio_status: str | None  # low | moderate | high
    debt_burden: float | None
    debt_burden_status: str | None
    cashflow_net: float
    cashflow_status: str  # positive | negative | neutral
    cashflow_streak: int
    upcoming_obligations_count: int
    upcoming_obligations_amount: float


class Insight(APIModel):
    key: str
    title: str
    description: str
    tone: str  # accent | positive | negative | warning | neutral


class AnalyticsResponse(APIModel):
    as_of: date
    period: PeriodWindow
    previous_period: PeriodWindow
    month_start_day: int
    currency: str
    has_data: bool
    transactions_count: int
    income: FlowSummary
    expenses: FlowSummary
    savings: SavingsSummary
    categories: list[CategoryBreakdown]
    net_worth: NetWorth
    net_worth_history: list[NetWorthHistoryPoint]
    budget: dict
    history: list[PeriodPoint]
    forecasts: Forecasts
    health: FinancialHealth
    insights: list[Insight]


class SafeToSpendCommitment(APIModel):
    kind: str  # recurring | debt
    description: str | None
    amount: float
    due_date: date | None


class SafeToSpendResponse(APIModel):
    status: str  # ok | insufficient
    reason: str | None
    is_estimate: bool
    available_money: float | None
    obligations: list[SafeToSpendCommitment]
    obligations_total: float | None
    planned_savings: float | None
    reserve_amount: float | None
    committed_total: float | None
    discretionary: float | None
    remaining_days: int | None
    safe_to_spend_daily: float | None
    explanation: str
    disclaimer: str