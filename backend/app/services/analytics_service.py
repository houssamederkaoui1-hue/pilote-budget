"""Central analytics engine: trends, history, forecasts, Safe-to-Spend.

This is the **only** place financial analytics are computed. The frontend
consumes the API output verbatim and never recomputes a money formula; the
health indicators, insights and estimates below are deterministic and derived
from real ledger data only.

Forecasting is intentionally conservative: an end-of-period estimate is the
straight-line pace seen so far (``actual / elapsed_days * period_days``), only
produced once a period has actual data, and always labeled as an estimate.
Historical net worth is reconstructed from the ledger as-of each period end,
never invented.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.analytics import (
    ASSET_TYPES,
    days_elapsed,
    days_in_period,
    is_liability_type,
    savings_rate,
    share_of,
    straight_line_projection,
    trend_from,
)
from app.domain.calculations import percent_change
from app.domain.enums import TransactionStatus, TransactionType
from app.domain.periods import period_end, period_start, previous_period_start
from app.domain.safetospend import calculate as safe_to_spend_formula
from app.models.account import Account
from app.models.category import Category
from app.models.debt import Debt
from app.models.profile import Profile
from app.models.transaction import Transaction
from app.services.balance_service import BalanceService
from app.services.budget_service import BudgetService
from app.services.overview_service import OverviewService
from app.services.profile_service import ProfileService
from app.services.recurring_service import RecurringService

POSTED = (
    TransactionStatus.PENDING,
    TransactionStatus.CLEARED,
    TransactionStatus.RECONCILED,
)

# Completed periods kept in the history series (current period is appended).
HISTORY_PERIODS = 6

# Financial-health thresholds (deterministic, documented).
SAVINGS_RATE_OK = 10.0
RECURRING_LOW = 30.0
RECURRING_HIGH = 60.0
DEBT_LOW = 30.0
DEBT_HIGH = 60.0


def _round(value: float | int | None) -> float:
    return round(float(value or 0.0), 2)


def _pct(change) -> float | None:
    """Decimal fraction from ``percent_change`` -> signed percentage number."""
    return None if change is None else round(float(change) * 100, 1)


class AnalyticsService:
    def __init__(self, session: Session):
        self.session = session
        self.profile = ProfileService(session)
        self.balances = BalanceService(session)
        # Per-request caches: the service instance lives for one API call, so
        # repeat reads (net-worth as-of per period, period summaries, profile)
        # collapse dozens of identical SQL statements into a single query.
        self._profile: Profile | None = None
        self._posted_count: int | None = None
        self._asof_cache: dict[date, tuple[float, float, float]] = {}
        self._balance_summaries: dict[tuple[date, date], dict] = {}
        self._expense_cache: dict[tuple[date, date], dict[int, float]] = {}
        self._debts_cache: list[Debt] | None = None

    # -- shared helpers ----------------------------------------------------

    def _get_profile(self) -> Profile:
        if self._profile is None:
            self._profile = self.profile.get()
        return self._profile

    def month_start_day(self) -> int:
        return self._get_profile().month_start_day

    def _window(self, start: date) -> dict:
        end = period_end(start, self.month_start_day())
        return {"period_start": start, "period_end": end, "closed": end < self.today}

    def _series(self, months: int | None = None) -> list[dict]:
        """Up to ``HISTORY_PERIODS`` past windows (oldest first) + current.

        ``months`` caps the *total* number of windows (including the current
        one), defaulting to the full history depth.
        """
        msd = self.month_start_day()
        cursor = self.today
        count = HISTORY_PERIODS + 1
        if months is not None:
            count = min(count, max(1, int(months)))
        starts: list[date] = []
        for _ in range(count):
            start = period_start(cursor, msd)
            if not starts or start != starts[-1]:
                starts.append(start)
            cursor = previous_period_start(cursor, msd)
        starts.reverse()
        return [self._window(start) for start in starts]

    def _balance_summary(self, start: date, end: date) -> dict:
        key = (start, end)
        if key not in self._balance_summaries:
            self._balance_summaries[key] = self.balances.summary(start, end)
        return self._balance_summaries[key]

    def _asof_worth(self, on: date) -> tuple[float, float, float]:
        """(assets, liabilities, net) balances as-of ``on`` (cached)."""
        if on not in self._asof_cache:
            bals = self.balances.compute_as_of(on)
            assets = round(sum(v for v in bals.values() if v > 0), 2)
            liabilities = round(sum(-v for v in bals.values() if v < 0), 2)
            self._asof_cache[on] = (assets, liabilities, round(assets - liabilities, 2))
        return self._asof_cache[on]

    def _active_debts(self) -> list[Debt]:
        if self._debts_cache is None:
            self._debts_cache = list(
                self.session.scalars(select(Debt).where(Debt.active.is_(True))).all()
            )
        return self._debts_cache

    def _posted_transactions_count(self) -> int:
        if self._posted_count is None:
            self._posted_count = int(
                self.session.scalar(
                    select(func.count(Transaction.id)).where(Transaction.status.in_(POSTED))
                )
                or 0
            )
        return self._posted_count

    # -- engine -------------------------------------------------------------

    def summary(self, today: date | None = None, months: int | None = None) -> dict:
        self.today = today or date.today()
        msd = self.month_start_day()

        start = period_start(self.today, msd)
        end = period_end(self.today, msd)
        prev_start = previous_period_start(self.today, msd)
        prev_end = period_end(prev_start, msd)

        has_data = self._posted_transactions_count() > 0

        cur = self._balance_summary(start, self.today)
        prev = self._balance_summary(prev_start, prev_end)

        income_change = _pct(percent_change(cur["income"], prev["income"]))
        expense_change = _pct(percent_change(cur["expense"], prev["expense"]))

        rate = savings_rate(cur["net"], cur["income"])
        rate_status = self._rate_status(rate)

        series = self._series(months)
        history_points: list[dict] = []
        for window in series:
            until = window["period_end"] if window["closed"] else self.today
            win = self._balance_summary(window["period_start"], until)
            history_points.append(
                {
                    "period_start": window["period_start"],
                    "period_end": window["period_end"],
                    "closed": window["closed"],
                    "income": win["income"],
                    "expense": win["expense"],
                    "net": win["net"],
                    "savings_rate": savings_rate(win["net"], win["income"]),
                }
            )

        closed_rates = [
            point["savings_rate"]
            for point in history_points
            if point["closed"] and point["savings_rate"] is not None
        ]
        historical_rate = (
            round(sum(closed_rates) / len(closed_rates), 1) if closed_rates else None
        )

        categories = self._category_breakdown(start, end, prev_start, prev_end)

        net_worth = self._net_worth(prev_end)
        history = self._net_worth_history(series)

        budget = BudgetService(self.session).summary(self.today)

        forecasts = self._forecasts(start, end, cur)

        obligations = self._obligations(start, end, self.today)
        health = self._health(cur, rate, rate_status, budget, obligations, net_worth, history_points)
        insights = self._insights(
            has_data,
            categories=categories,
            cur=cur,
            prev=prev,
            rate=rate,
            rate_status=rate_status,
            budget=budget,
            net_worth=net_worth,
            obligations=obligations,
            history_points=history_points,
        )

        profile = self._get_profile()
        return {
            "as_of": self.today,
            "period": {
                "period_start": start,
                "period_end": end,
                "closed": False,
            },
            "previous_period": {
                "period_start": prev_start,
                "period_end": prev_end,
                "closed": True,
            },
            "month_start_day": msd,
            "currency": profile.currency,
            "has_data": has_data,
            "transactions_count": self._posted_transactions_count(),
            "income": {
                "current": cur["income"],
                "previous": prev["income"],
                "change_pct": income_change,
                "trend": trend_from(income_change),
            },
            "expenses": {
                "current": cur["expense"],
                "previous": prev["expense"],
                "change_pct": expense_change,
                "trend": trend_from(expense_change),
            },
            "savings": {
                "current": cur["net"],
                "previous": prev["net"],
                "change_pct": _pct(percent_change(cur["net"], prev["net"])),
                "rate": rate,
                "rate_status": rate_status,
                "historical_rate": historical_rate,
            },
            "categories": categories,
            "net_worth": net_worth,
            "net_worth_history": history,
            "budget": budget,
            "history": history_points,
            "forecasts": forecasts,
            "health": health,
            "insights": insights,
        }

    # -- category breakdown -------------------------------------------------

    def _category_breakdown(
        self, start: date, end: date, prev_start: date, prev_end: date
    ) -> list[dict]:
        current = self._expense_by_category(start, end)
        previous = self._expense_by_category(prev_start, prev_end)
        total = round(sum(current.values()) or 0.0, 2)

        if not current:
            return []

        names = {
            category.id: category.name
            for category in self.session.scalars(
                select(Category).where(Category.id.in_(list(current)))
            ).all()
        }

        items = []
        for category_id, amount in sorted(current.items(), key=lambda kv: kv[1], reverse=True):
            prev_amount = previous.get(category_id)
            items.append(
                {
                    "category_id": category_id,
                    "category_name": names.get(category_id, "Uncategorized"),
                    "amount": round(amount, 2),
                    "share_pct": share_of(amount, total),
                    "change_pct": (
                        _pct(percent_change(amount, prev_amount))
                        if prev_amount is not None
                        else None
                    ),
                }
            )
        return items

    def _expense_by_category(self, start: date, end: date) -> dict[int, float]:
        key = (start, end)
        if key not in self._expense_cache:
            rows = self.session.execute(
                select(
                    Transaction.category_id,
                    func.sum(Transaction.amount),
                )
                .where(
                    Transaction.type == TransactionType.EXPENSE,
                    Transaction.status.in_(POSTED),
                    Transaction.date >= start,
                    Transaction.date <= end,
                    Transaction.category_id.is_not(None),
                )
                .group_by(Transaction.category_id)
            ).all()
            self._expense_cache[key] = {
                category_id: round(total, 2) for category_id, total in rows
            }
        return self._expense_cache[key]

    # -- net worth (accounts as-of, plus debt-adjusted current) ---------------

    def _net_worth(self, prev_end: date) -> dict:
        assets, liabilities, net = self._asof_worth(self.today)
        previous = self._asof_worth(prev_end)[2]
        debt_adjusted = OverviewService(self.session).get()["net_worth"]
        return {
            "assets": assets,
            "liabilities": liabilities,
            "net_worth": net,
            "net_worth_including_debts": debt_adjusted,
            "previous": previous,
            "change_pct": _pct(percent_change(net, previous)),
        }

    def _net_worth_history(self, series: list[dict]) -> list[dict]:
        points = []
        for window in series:
            on = window["period_end"] if window["closed"] else self.today
            assets, liabilities, net = self._asof_worth(on)
            points.append(
                {
                    "period_start": window["period_start"],
                    "period_end": window["period_end"],
                    "closed": window["closed"],
                    "assets": assets,
                    "liabilities": liabilities,
                    "net_worth": net,
                }
            )
        return points

    # -- forecasts -------------------------------------------------------------

    def _forecasts(self, start: date, end: date, cur: dict) -> dict:
        elapsed = days_elapsed(start, self.today)
        total = days_in_period(start, end)
        is_estimate = elapsed > 0

        est_income = straight_line_projection(cur["income"], elapsed, total)
        est_spending = straight_line_projection(cur["expense"], elapsed, total)
        est_savings = (
            round(float(est_income or 0.0) - float(est_spending or 0.0), 2)
            if est_income is not None and est_spending is not None
            else None
        )

        opening = self._asof_worth(start - timedelta(days=1))[2]
        current_available = self._asof_worth(self.today)[2]
        estimated_end = (
            round(opening + (est_savings or 0.0), 2)
            if est_savings is not None
            else None
        )

        return {
            "spending": {
                "actual": cur["expense"],
                "estimated": est_spending,
                "is_estimate": is_estimate,
            },
            "income": {
                "actual": cur["income"],
                "estimated": est_income,
                "is_estimate": is_estimate,
            },
            "savings": {
                "actual": cur["net"],
                "estimated": est_savings,
                "is_estimate": is_estimate,
            },
            "available": {
                "opening": opening,
                "current": current_available,
                "estimated_end": estimated_end,
                "is_estimate": est_savings is not None,
            },
            "note": (
                "Conservative straight-line estimate from the pace so far; "
                "actual results will differ."
            ),
        }

    # -- obligations (used by health + insights + Safe-to-Spend) ---------------

    def _obligations(self, start: date, end: date, from_date: date) -> list[dict]:
        """Expense obligations due within the period ``[start, end]``.

        Recurring due dates and debt minimum payments are projected for the
        whole period; anything already past ``from_date`` is flagged ``overdue``
        instead of being dropped — a bill that should have been paid is still
        committed money, so Safe-to-Spend keeps it in the pool.
        """
        obligations: list[dict] = []
        total_days = max(1, days_in_period(start, end))
        projection = RecurringService(self.session).upcoming(start, days=total_days)
        for occurrence in projection["occurrences"]:
            due = occurrence["due_date"]
            if due < start or due > end:
                continue
            if occurrence["type"] != TransactionType.EXPENSE.value:
                continue
            obligations.append(
                {
                    "kind": "recurring",
                    "description": occurrence["description"]
                    or occurrence["category_name"]
                    or f"Recurring {occurrence['frequency']}",
                    "amount": round(float(occurrence["amount"]), 2),
                    "due_date": due,
                    "overdue": due < from_date,
                }
            )

        for debt in self._active_debts():
            due = debt.due_date
            if due is None or due < start or due > end:
                continue
            if debt.minimum_payment is None:
                continue
            obligations.append(
                {
                    "kind": "debt",
                    "description": debt.name,
                    "amount": round(float(debt.minimum_payment), 2),
                    "due_date": due,
                    "overdue": due < from_date,
                }
            )

        obligations.sort(key=lambda item: item["due_date"])
        return obligations

    # -- financial health -------------------------------------------------------

    def _rate_status(self, rate: float | None) -> str:
        if rate is None:
            return "insufficient"
        if rate >= SAVINGS_RATE_OK:
            return "positive"
        if rate >= 0:
            return "neutral"
        return "negative"

    @staticmethod
    def _health_threshold(value: float | None, low: float, high: float) -> str | None:
        if value is None:
            return None
        if value < low:
            return "low"
        if value <= high:
            return "moderate"
        return "high"

    def _recurring_ratio(self, start: date, end: date, expense_total: float) -> float | None:
        if expense_total <= 0:
            return None
        total_days = days_in_period(start, end)
        projection = RecurringService(self.session).upcoming(start, days=total_days)
        recurring_due = sum(
            round(float(o["amount"]), 2)
            for o in projection["occurrences"]
            if o["type"] == TransactionType.EXPENSE.value and start <= o["due_date"] <= end
        )
        debt_due = 0.0
        for debt in self._active_debts():
            if debt.due_date is None or debt.minimum_payment is None:
                continue
            if start <= debt.due_date <= end:
                debt_due += round(float(debt.minimum_payment), 2)
        return round((recurring_due + debt_due) / expense_total * 100, 1)

    def _debt_burden(self, assets: float) -> float | None:
        if assets <= 0:
            return None
        total_remaining = round(
            sum((d.remaining_amount for d in self._active_debts()))
            or 0.0,
            2,
        )
        return round(total_remaining / assets * 100, 1)

    def _health(
        self,
        cur: dict,
        rate: float | None,
        rate_status: str,
        budget: dict,
        obligations: list[dict],
        net_worth: dict,
        history_points: list[dict],
    ) -> dict:
        recurring_ratio = self._recurring_ratio(
            budget["period_start"], budget["period_end"], cur["expense"]
        )
        debt_burden = self._debt_burden(net_worth["assets"])

        streak = 0
        for point in reversed(history_points):
            if not point["closed"]:
                continue
            if point["net"] > 0:
                streak += 1
            else:
                break
        cashflow_status = "positive" if cur["net"] > 0 else "negative" if cur["net"] < 0 else "neutral"

        return {
            "savings_rate": rate,
            "savings_rate_status": rate_status,
            "budget_pct_used": budget["totals"]["pct_used"],
            "budget_over": budget["totals"]["over_budget"],
            "recurring_expense_ratio": recurring_ratio,
            "recurring_expense_ratio_status": self._health_threshold(
                recurring_ratio, RECURRING_LOW, RECURRING_HIGH
            ),
            "debt_burden": debt_burden,
            "debt_burden_status": self._health_threshold(debt_burden, DEBT_LOW, DEBT_HIGH),
            "cashflow_net": cur["net"],
            "cashflow_status": cashflow_status,
            "cashflow_streak": streak,
            "upcoming_obligations_count": len(obligations),
            "upcoming_obligations_amount": round(sum(o["amount"] for o in obligations), 2),
        }

    # -- insights ---------------------------------------------------------------

    def _insights(
        self,
        has_data: bool,
        *,
        categories: list[dict],
        cur: dict,
        prev: dict,
        rate: float | None,
        rate_status: str,
        budget: dict,
        net_worth: dict,
        obligations: list[dict],
        history_points: list[dict],
    ) -> list[dict]:
        if not has_data:
            return [
                {
                    "key": "no-data",
                    "title": "Insufficient data",
                    "description": "Record or import transactions; trends and insights appear once the ledger has entries.",
                    "tone": "neutral",
                }
            ]

        insights: list[dict] = []

        if categories:
            head = categories[0]
            insights.append(
                {
                    "key": "top-category",
                    "title": f"Top spending: {head['category_name']}",
                    "description": (
                        f"{head['amount']:.2f} this period — "
                        f"{head['share_pct']:.0f}% of spending."
                        if head["share_pct"] is not None
                        else f"{head['amount']:.2f} this period."
                    ),
                    "tone": "accent",
                }
            )

        expense_change = _pct(percent_change(cur["expense"], prev["expense"]))
        if expense_change is not None and abs(expense_change) >= 1:
            direction = "up" if expense_change > 0 else "down"
            insights.append(
                {
                    "key": "expense-trend",
                    "title": f"Spending is {direction}",
                    "description": f"{abs(expense_change):.0f}% vs the previous period.",
                    "tone": "warning" if direction == "up" else "positive",
                }
            )

        if rate is not None:
            tone = {
                "positive": "positive",
                "negative": "negative",
                "neutral": "neutral",
            }.get(rate_status, "neutral")
            verb = (
                "healthy"
                if rate_status == "positive"
                else "negative"
                if rate_status == "negative"
                else "flat"
            )
            insights.append(
                {
                    "key": "savings-rate",
                    "title": f"Savings rate {rate:.0f}%",
                    "description": f"Net of expenses vs income this period ({verb}).",
                    "tone": tone,
                }
            )

        over_items = [item for item in budget["items"] if item["over_budget"]]
        if over_items:
            names = ", ".join(item["category_name"] for item in over_items[:3])
            insights.append(
                {
                    "key": "budget-over",
                    "title": "Budget overruns",
                    "description": f"Over budget: {names}{'…' if len(over_items) > 3 else ''}.",
                    "tone": "negative",
                }
            )
        else:
            insights.append(
                {
                    "key": "budget-under",
                    "title": "Within budget",
                    "description": "No category is currently over its plan this period.",
                    "tone": "positive",
                }
            )

        if obligations:
            total = round(sum(o["amount"] for o in obligations), 2)
            insights.append(
                {
                    "key": "obligations",
                    "title": f"{len(obligations)} upcoming obligation(s)",
                    "description": f"{total:.2f} is committed before the next period.",
                    "tone": "neutral",
                }
            )

        if net_worth["previous"] is not None and net_worth["change_pct"] is not None:
            change = net_worth["change_pct"]
            net_tone = "positive" if change >= 0 else "negative"
            insights.append(
                {
                    "key": "net-worth-change",
                    "title": f"Net worth is {net_tone}",
                    "description": f"{change:+.0f}% vs the previous period end.",
                    "tone": net_tone,
                }
            )

        streak = 0
        for point in reversed(history_points):
            if not point["closed"]:
                continue
            if point["net"] > 0:
                streak += 1
            else:
                break
        if streak >= 2:
            insights.append(
                {
                    "key": "cashflow-streak",
                    "title": f"{streak} positive month(s) in a row",
                    "description": "Income has exceeded expenses recently.",
                    "tone": "positive",
                }
            )

        return insights[:6]

    # -- Safe-to-Spend -----------------------------------------------------------

    def safe_to_spend(self, today: date | None = None) -> dict:
        self.today = today or date.today()
        msd = self.month_start_day()
        start = period_start(self.today, msd)
        end = period_end(self.today, msd)

        disclaimer = (
            "Safe-to-Spend is a planning estimate, not financial advice. "
            "Projected obligations are paid only when you record them; treat "
            "the daily figure as guidance."
        )

        if self._posted_transactions_count() == 0:
            return {
                "status": "insufficient",
                "reason": "No recorded transactions yet — there is no ledger to base the estimate on.",
                "is_estimate": False,
                "available_money": None,
                "obligations": [],
                "obligations_total": None,
                "planned_savings": None,
                "reserve_amount": None,
                "committed_total": None,
                "discretionary": None,
                "remaining_days": None,
                "safe_to_spend_daily": None,
                "explanation": (
                    "Cannot calculate Safe-to-Spend without a transaction history; "
                    "record an income or expense to unlock this estimate."
                ),
                "disclaimer": disclaimer,
            }

        available = self._available_money()

        obligations = self._obligations(start, end, self.today)
        obligations_total = round(sum(o["amount"] for o in obligations), 2)

        budget = BudgetService(self.session).summary(self.today)
        planned_savings = round(float(budget["allocation"]["savings_amount"]), 2)

        preferences = self.profile.get().preferences or {}
        try:
            reserve = round(float(preferences.get("minimum_reserve") or 0.0), 2)
        except (TypeError, ValueError):
            reserve = 0.0

        remaining_days = days_in_period(self.today, end)

        breakdown = safe_to_spend_formula(
            available,
            obligations_total,
            planned_savings,
            reserve,
            remaining_days,
        )

        return {
            "status": "ok",
            "reason": None,
            "is_estimate": True,
            "available_money": breakdown["available"],
            "obligations": obligations,
            "obligations_total": breakdown["obligations"],
            "planned_savings": breakdown["planned_savings"],
            "reserve_amount": breakdown["reserve"],
            "committed_total": breakdown["committed"],
            "discretionary": breakdown["discretionary"],
            "remaining_days": breakdown["remaining_days"],
            "safe_to_spend_daily": breakdown["daily"],
            "explanation": breakdown["explanation"],
            "disclaimer": disclaimer,
        }

    def _available_money(self) -> float:
        """Money currently usable: active asset balances minus owed amounts.

        Asset accounts (checking, savings, cash, ...) contribute their balance
        (an overdraft reduces availability) only while active — archived money
        is frozen and not spendable today. Owed balances on liability accounts
        are always subtracted, archived or not: a credit-card debt does not
        disappear when the account is archived.
        """
        accounts = self.session.scalars(select(Account)).all()
        balances = self.balances.compute_all()

        available = 0.0
        for account in accounts:
            balance = balances.get(account.id, 0.0)
            if account.type in ASSET_TYPES:
                if account.active:
                    available += balance
            elif is_liability_type(account.type):
                available -= max(0.0, -balance)
        return round(available, 2)