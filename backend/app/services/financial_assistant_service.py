"""Financial Assistant service: state assembly + deterministic Q&A.

The pure domain module (``app.domain.financial_assistant``) owns every formula;
this layer only:

1. assembles the ``state`` payload the pure engine consumes, sourcing numbers
   from the analytics engine, Safe-to-Spend, goals and debts, and
2. wires currency formatting via injected ``Formatters``.

All values mirror real ledger data; nothing is invented here.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.domain.analytics import days_elapsed, days_in_period
from app.domain.currency import FALLBACK_SYMBOL, symbol_for
from app.domain.financial_assistant import (
    QUESTIONS,
    Formatters,
    answer_question,
    compose_overview,
    generate_insights,
    greeting,
    match_intent,
    prioritize,
)
from app.services.analytics_service import AnalyticsService
from app.services.assistant_provider import get_assistant_provider
from app.services.goal_service import GoalService
from app.services.profile_service import ProfileService
from app.services.recurring_service import RecurringService

MONTH_NAMES = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def _money(value) -> str:
    amount = float(value or 0.0)
    if abs(amount) < 0.005:
        amount = 0.0
    if amount < 0:
        return f"-{FALLBACK_SYMBOL}{abs(amount):,.2f}"
    return f"{FALLBACK_SYMBOL}{amount:,.2f}"


def _pct(value, digits: int) -> str:
    if value is None:
        return "n/a"
    return f"{value:,.{int(digits)}f}%"


def _currency_symbol(currency: str | None) -> str:
    return symbol_for(currency)


def _money_formatter(symbol: str):
    def money(value) -> str:
        amount = float(value or 0.0)
        if abs(amount) < 0.005:
            amount = 0.0
        if amount < 0:
            return f"-{symbol}{abs(amount):,.2f}"
        return f"{symbol}{amount:,.2f}"

    return money


def _period_label(start: date, end: date) -> str:
    start_label = f"{MONTH_NAMES[start.month - 1]} {start.day}"
    end_label = f"{MONTH_NAMES[end.month - 1]} {end.day}, {end.year}"
    if start.year != end.year:
        start_label += f", {start.year}"
    return f"{start_label} – {end_label}"


class FinancialAssistantService:
    def __init__(self, session: Session):
        self.session = session
        self.analytics = AnalyticsService(session)

    def _formatters(self) -> Formatters:
        symbol = _currency_symbol(ProfileService(self.session).get().currency)
        return Formatters(money=_money_formatter(symbol), pct=_pct)

    @staticmethod
    def _income_basis(summary: dict) -> float | None:
        """Typical monthly income: avg of completed months, else current."""
        closed = [
            point["income"]
            for point in summary.get("history", [])
            if point.get("closed") and (point.get("income") or 0) > 0
        ]
        if closed:
            return round(sum(closed) / len(closed), 2)
        current = summary["income"]["current"]
        if current and current > 0:
            return round(current, 2)
        return None

    @staticmethod
    def _obligation_splits(safe: dict | None) -> tuple[float, float]:
        """(monthly recurring, monthly debt) from the Safe-to-Spend plan."""
        if not safe or safe.get("status") != "ok":
            return 0.0, 0.0
        recurring = 0.0
        debt = 0.0
        for obligation in safe.get("obligations") or []:
            if obligation.get("kind") == "recurring":
                recurring += float(obligation.get("amount") or 0)
            elif obligation.get("kind") == "debt":
                debt += float(obligation.get("amount") or 0)
        return round(recurring, 2), round(debt, 2)

    # -- engine wiring ------------------------------------------------------

    def _state(self, today: date) -> dict:
        summary = self.analytics.summary(today=today)
        safe = self.analytics.safe_to_spend(today=today)
        profile = ProfileService(self.session).get()

        period = summary["period"]
        start = period["period_start"]
        end = period["period_end"]

        recurring, debt_minimums = self._obligation_splits(safe)

        state = {
            "has_data": summary["has_data"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "currency": profile.currency,
            "period": {"period_start": start, "period_end": end},
            "previous_period": summary["previous_period"],
            "analytics": summary,
            "safe_to_spend": safe if safe.get("status") == "ok" else None,
            "goals": [
                goal for goal in GoalService(self.session).list(today=today)
                if goal.get("active")
            ],
            "income_basis": self._income_basis(summary),
            "monthly_recurring": recurring,
            "monthly_debt_minimums": debt_minimums,
            "upcoming": RecurringService(self.session).upcoming(today=today, days=15),
            "projection": {
                "elapsed": days_elapsed(start, today),
                "total": days_in_period(start, end),
            },
        }
        state["insights"] = prioritize(
            generate_insights(state, self._formatters())
        )
        return state

    # -- public API -----------------------------------------------------------

    def overview(self, today: date | None = None) -> dict:
        today = today or date.today()
        state = self._state(today)
        fmt = self._formatters()
        summary = state["analytics"]
        period = summary["period"]
        label = _period_label(period["period_start"], period["period_end"])

        provider = get_assistant_provider(self.session)
        insights = state["insights"]
        overview_text = provider.draft_overview(compose_overview(state, fmt, label))

        return {
            "provider": provider.id,
            "provider_name": provider.name,
            "generated_at": state["generated_at"],
            "period": {
                "period_start": period["period_start"],
                "period_end": period["period_end"],
            },
            "currency": state["currency"],
            "has_data": state["has_data"],
            "greeting": greeting(),
            "overview": overview_text,
            "insights": insights,
            "questions": QUESTIONS,
        }

    def ask(
        self,
        question: str,
        *,
        intent: str | None = None,
        goal_id: int | None = None,
        today: date | None = None,
    ) -> dict:
        today = today or date.today()
        state = self._state(today)
        fmt = self._formatters()
        resolved = intent or (match_intent(question) if question else None)
        if not resolved:
            resolved = "unknown"
        return answer_question(state, resolved, fmt, goal_id=goal_id, question=question)