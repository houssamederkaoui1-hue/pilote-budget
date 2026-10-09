"""Financial Assistant: deterministic insight engine + structured questions.

This module is **pure**: it has no database, HTTP or framework imports. It turns
a plain ``state`` dictionary (assembled by the assistant service from the
analytics engine and the ledger) into prioritized, explainable insights and
answers to structured questions.

The assistant **never invents data**. Every number below either comes from the
``state`` payload (which mirrors real ledger facts) or is derived from it with
an explicit, documented formula. Projections reuse the same conservative
straight-line helper as the analytics engine and every estimate is labeled.

Text is produced through injected formatters (``money`` / ``pct``) so the
domain stays currency-agnostic and testable; the service wires them to the
profile currency.

Intent classifier: provider-independent structured questions are answered
solely with these deterministic calculations.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Callable

from app.domain.analytics import straight_line_projection

# -- published limits (kept small on purpose: no insight spam) ---------------

MAX_INSIGHTS = 8
MAX_PER_CATEGORY = {"spending": 2, "budget": 2, "goals": 1}

# Thresholds for deciding *whether* an observation is worth surfacing.
CATEGORY_CHANGE_THRESHOLD = 15.0      # % vs last period before flagging
TOP_CATEGORY_SHARE = 33.0             # % of spending before "largest category"
BUDGET_WARN_PCT = 85.0                # % of a budget used before warning
BUDGET_OVER_PCT = 100.0
SAVINGS_IMPROVEMENT_PTS = 3.0         # savings-rate points moved up/down
RECURRING_RATIO_INFO = 25.0           # % of monthly income
RECURRING_RATIO_WARN = 50.0
DEBT_RATIO_INFO = 15.0
DEBT_RATIO_WARN = 30.0
DEBT_RATIO_CRITICAL = 40.0
NETWORTH_UP_SUCCESS = 10.0            # % change
NETWORTH_DOWN_WARN = -5.0
GOAL_SOON_MONTHS = 6
GOAL_FINE_MONTHS = 12
CASHFLOW_CRITICAL_LEVEL = 1000.0      # projected deficit magnitude (currency)

# Supported structured questions (drives both the UI chips and intent labels).
QUESTIONS: list[dict[str, str]] = [
    {"intent": "spending", "question": "How much did I spend this month?"},
    {"intent": "top_categories", "question": "Where am I spending the most?"},
    {"intent": "budget_status", "question": "Am I on track with my budget?"},
    {"intent": "safe_to_spend", "question": "How much can I safely spend today?"},
    {"intent": "savings", "question": "How much did I save?"},
    {"intent": "net_worth", "question": "How is my net worth changing?"},
    {"intent": "net_worth_contributors", "question": "What is driving my net worth?"},
    {"intent": "expense_increases", "question": "Which expenses increased?"},
    {"intent": "insights", "question": "What should I pay attention to?"},
    {"intent": "upcoming", "question": "What bills are coming up?"},
    {"intent": "goals_progress", "question": "How are my goals progressing?"},
    {"intent": "goal_eta", "question": "When will I reach my goal?"},
]

INTENT_LABELS = {item["intent"]: item for item in QUESTIONS}


@dataclass(frozen=True)
class Formatters:
    """Currency-agnostic text formatters injected by the service layer."""

    money: Callable[[float], str]
    pct: Callable[[float, int], str]


def metric(*, kind: str, unit: str = "currency", label=None, current=None,
           previous=None, change_pct=None) -> dict:
    """Build a ``metric`` payload (the numbers behind an insight)."""
    return {
        "kind": kind,
        "label": label,
        "current": current,
        "previous": previous,
        "change_pct": change_pct,
        "unit": unit,
    }


def _insight(*, id: str, severity: str, category: str, title: str,
             explanation: str, m: dict | None, actionable: bool = False,
             priority: int = 0, generated_at: str | None = None) -> dict:
    return {
        "id": id,
        "severity": severity,
        "category": category,
        "title": title,
        "explanation": explanation,
        "metric": m,
        "actionable": actionable,
        "priority": priority,
        "generated_at": generated_at,
    }


# -- insight generation -------------------------------------------------------


def generate_insights(state: dict, fmt: Formatters) -> list[dict]:
    """All candidate insights from a state payload (see module docs)."""
    if not state.get("has_data"):
        return [
            _insight(
                id="no-data",
                severity="info",
                category="overview",
                title="Nothing to analyze yet",
                explanation=(
                    "Record or import transactions first — the assistant can only "
                    "describe what is actually in your ledger."
                ),
                m=None,
                actionable=False,
                priority=0,
            )
        ]

    result: list[dict] = []
    a = state["analytics"]
    generated_at = state.get("generated_at")
    nw = a.get("net_worth") or {}
    budget = a.get("budget") or {}
    forecasts = a.get("forecasts") or {}

    # -- spending -------------------------------------------------------------
    for item in _spending_category_insights(a.get("categories") or [], fmt):
        item["generated_at"] = generated_at
        result.append(item)

    # -- budget ---------------------------------------------------------------
    for item in _budget_insights(
        budget, state.get("projection") or {}, fmt,
    ):
        item["generated_at"] = generated_at
        result.append(item)

    # -- savings --------------------------------------------------------------
    savings = a.get("savings") or {}
    history = a.get("history") or []
    item = _savings_insight(savings, history, fmt)
    if item:
        item["generated_at"] = generated_at
        result.append(item)

    # -- recurring + debt income ratios ---------------------------------------
    income_basis = state.get("income_basis")
    if income_basis and income_basis > 0:
        recurring_ins = _recurring_ratio_insight(
            state.get("monthly_recurring", 0.0), income_basis, fmt, generated_at
        )
        if recurring_ins:
            result.append(recurring_ins)
        debt_ins = _debt_ratio_insight(
            state.get("monthly_debt_minimums", 0.0), income_basis, fmt, generated_at
        )
        if debt_ins:
            result.append(debt_ins)

    # -- cashflow + net worth ---------------------------------------------------
    item = _cashflow_insight(forecasts, fmt)
    if item:
        item["generated_at"] = generated_at
        result.append(item)

    item = _net_worth_insight(nw, fmt)
    if item:
        item["generated_at"] = generated_at
        result.append(item)

    health = a.get("health") or {}
    item = _cashflow_streak_insight(health)
    if item:
        result.append(item)

    # -- safe-to-spend ----------------------------------------------------------
    item = _safe_to_spend_insight(state.get("safe_to_spend"), fmt)
    if item:
        item["generated_at"] = generated_at
        result.append(item)

    # -- goals -----------------------------------------------------------------
    for goal_item in _goal_eta_insights(state.get("goals") or [], fmt, generated_at):
        result.append(goal_item)

    return result


def _previous_amount(item: dict) -> float | None:
    """Derive last period's amount from ``amount`` and ``change_pct``."""
    pct = item.get("change_pct")
    amount = item.get("amount") or 0
    if pct is None or pct <= -100:
        return None
    return round(amount / (1 + pct / 100), 2)


def _spending_category_insights(categories: list[dict], fmt: Formatters) -> list[dict]:
    insights: list[dict] = []
    changes = [
        c for c in categories
        if (c.get("change_pct") or 0) >= CATEGORY_CHANGE_THRESHOLD and c.get("amount")
    ]
    for item in changes[:2]:
        preceding = _previous_amount(item)
        pct = item["change_pct"]
        name = item.get("category_name") or "uncategorized"
        explanation = f"You spent {fmt.money(item['amount'])} on {name} this period"
        if preceding is not None:
            explanation += f" vs {fmt.money(preceding)} last period."
        else:
            explanation += "."
        insights.append(
            _insight(
                id=f"category-up-{name.lower().replace(' ', '-')}",
                severity="warning" if pct >= 25 else "info",
                category="spending",
                title=f"{name} spending is {fmt.pct(pct, 0)} higher than last month",
                explanation=explanation,
                m=metric(
                    kind="category_change", label=name,
                    current=item["amount"], previous=preceding,
                    change_pct=pct,
                ),
                actionable=True,
                priority=80,
            )
        )
    if categories and (categories[0].get("share_pct") or 0) >= TOP_CATEGORY_SHARE:
        top = categories[0]
        name = top.get("category_name") or "uncategorized"
        insights.append(
            _insight(
                id="top-category",
                severity="info",
                category="spending",
                title=f"{name} is your largest expense",
                explanation=(
                    f"{name} accounts for {fmt.pct(top['share_pct'], 0)} of your "
                    f"spending this period ({fmt.money(top['amount'])})."
                ),
                m=metric(
                    kind="category_share", label=name,
                    current=top["amount"], change_pct=top["share_pct"], unit="percent",
                ),
                actionable=False,
                priority=40,
            )
        )
    return sorted(insights, key=lambda i: (-i["priority"], i["id"]))


def _budget_insights(budget: dict, projection: dict, fmt: Formatters) -> list[dict]:
    items = budget.get("items") or []
    planned_total = budget.get("totals", {}).get("planned") or 0
    candidates: list[dict] = []
    for item in items:
        items_to_consider = (item.get("planned_amount") or 0) > 0
        if not items_to_consider:
            continue
        planned = item["planned_amount"]
        actual = item.get("actual_amount") or 0
        pct_used = item.get("pct_used") or 0
        projected = None
        if projection and (projection.get("elapsed") or 0) > 0:
            projected = straight_line_projection(
                actual, projection["elapsed"], projection["total"]
            )
        candidates.append(
            (pct_used, projected or 0, planned, item, actual)
        )

    ordered = sorted(candidates, key=lambda row: -(row[0] or 0))
    for pct_used, projected, planned, item, actual in ordered[:2]:
        name = item.get("category_name") or "uncategorized"
        if pct_used >= BUDGET_OVER_PCT:
            insights = _insight(
                id=f"budget-over-{name.lower().replace(' ', '-')}",
                severity="critical",
                category="budget",
                title=f"{name} budget exceeded",
                explanation=(
                    f"You have used {fmt.pct(pct_used, 0)} of the {name} budget "
                    f"({fmt.money(actual)} of {fmt.money(planned)})."
                ),
                m=metric(
                    kind="budget_utilization", label=name,
                    current=actual, previous=planned, change_pct=pct_used, unit="percent",
                ),
                actionable=True,
                priority=95,
            )
        elif pct_used >= BUDGET_WARN_PCT:
            insights = _insight(
                id=f"budget-close-{name.lower().replace(' ', '-')}",
                severity="warning",
                category="budget",
                title=f"You have already used {fmt.pct(pct_used, 0)} of your {name} budget",
                explanation=(
                    f"{fmt.money(actual)} of the {fmt.money(planned)} planned is spent; "
                    "keep an eye on the rest of the period."
                ),
                m=metric(
                    kind="budget_utilization", label=name,
                    current=actual, previous=planned, change_pct=pct_used, unit="percent",
                ),
                actionable=True,
                priority=90,
            )
        elif projected and planned > 0 and projected > planned:
            insights = _insight(
                id=f"budget-projected-{name.lower().replace(' ', '-')}",
                severity="warning",
                category="budget",
                title=f"On track to exceed your {name} budget",
                explanation=(
                    f"At the current pace you would spend about "
                    f"{fmt.money(projected)} vs a {fmt.money(planned)} plan "
                    f"({fmt.money(actual)} spent so far)."
                ),
                m=metric(
                    kind="budget_projection", label=name,
                    current=projected, previous=planned, unit="currency",
                ),
                actionable=True,
                priority=85,
            )
        else:
            continue
        yield insights

    total_pct_used = budget.get("totals", {}).get("pct_used")
    if planned_total and total_pct_used is not None and total_pct_used >= BUDGET_WARN_PCT:
        total_pct = total_pct_used
        yield _insight(
            id="budget-total",
            severity="warning",
            category="budget",
            title=f"Overall, {fmt.pct(total_pct, 0)} of your monthly budget is used",
            explanation=(
                f"{fmt.money(budget['totals']['actual'])} spent against "
                f"{fmt.money(planned_total)} planned."
            ),
            m=metric(
                kind="budget_utilization", label="Overall budget",
                current=budget["totals"]["actual"], previous=planned_total,
                change_pct=total_pct, unit="percent",
            ),
            actionable=False,
            priority=45,
        )


def _savings_insight(savings: dict, history: list[dict], fmt: Formatters) -> dict | None:
    rate = savings.get("rate")
    if rate is None:
        return None

    previous_rate = None
    for point in reversed(history[:-1]):
        if point.get("closed") and point.get("savings_rate") is not None:
            previous_rate = point["savings_rate"]
            break

    if previous_rate is not None and abs(rate - previous_rate) >= SAVINGS_IMPROVEMENT_PTS:
        if rate > previous_rate:
            alias = "net" if rate < 0 else "savings rate"
            return _insight(
                id="savings-rate-improved",
                severity="success",
                category="savings",
                title="Your savings rate improved this month",
                explanation=(
                    f"Savings rose from {fmt.pct(previous_rate, 0)}% of income last "
                    f"period to {fmt.pct(rate, 0)}% this period."
                ),
                m=metric(
                    kind="savings_rate", current=rate, previous=previous_rate,
                    change_pct=round(rate - previous_rate, 1), unit="percent",
                ),
                actionable=False,
                priority=70,
            )
        return _insight(
            id="savings-rate-declined",
            severity="warning",
            category="savings",
            title="Your savings rate declined this month",
            explanation=(
                f"Savings fell from {fmt.pct(previous_rate, 0)}% of income last "
                f"period to {fmt.pct(rate, 0)}% this period."
            ),
            m=metric(
                kind="savings_rate", current=rate, previous=previous_rate,
                change_pct=round(rate - previous_rate, 1), unit="percent",
            ),
            actionable=True,
            priority=72,
        )

    if rate < 0:
        return _insight(
            id="savings-negative",
            severity="critical" if rate <= -20 else "warning",
            category="savings",
            title="Your savings are negative this month",
            explanation=(
                f"Spending exceeded income by {fmt.money(abs(savings['current']))} "
                "this period."
            ),
            m=metric(
                kind="savings", current=savings["current"],
                previous=savings.get("previous"),
                change_pct=savings.get("change_pct"),
            ),
            actionable=True,
            priority=78,
        )
    return None


def _recurring_ratio_insight(recurring_monthly: float, income: float, fmt: Formatters,
                             generated_at: str | None) -> dict | None:
    if recurring_monthly <= 0:
        return None
    ratio = recurring_monthly / income * 100
    if ratio < RECURRING_RATIO_INFO:
        return None
    return _insight(
        id="recurring-income-share",
        severity="warning" if ratio >= RECURRING_RATIO_WARN else "info",
        category="recurring",
        title=f"Recurring expenses represent {fmt.pct(ratio, 0)} of your monthly income",
        explanation=(
            f"{fmt.money(recurring_monthly)} in scheduled and debt commitments is due "
            f"before next period against {fmt.money(income)} of typical income."
        ),
        m=metric(
            kind="recurring_ratio", current=ratio, unit="percent", label="Recurring",
        ),
        actionable=True if ratio >= RECURRING_RATIO_WARN else False,
        priority=65,
        generated_at=generated_at,
    )


def _debt_ratio_insight(debt_monthly: float, income: float, fmt: Formatters,
                        generated_at: str | None) -> dict | None:
    if debt_monthly <= 0:
        return None
    ratio = debt_monthly / income * 100
    if ratio < DEBT_RATIO_INFO:
        return None
    severity = "critical" if ratio >= DEBT_RATIO_CRITICAL else (
        "warning" if ratio >= DEBT_RATIO_WARN else "info"
    )
    return _insight(
        id="debt-income-share",
        severity=severity,
        category="debt",
        title=f"Your debt payments represent {fmt.pct(ratio, 0)} of your monthly income",
        explanation=(
            f"{fmt.money(debt_monthly)} of minimum payments is due this period against "
            f"{fmt.money(income)} of typical income."
        ),
        m=metric(
            kind="debt_ratio", current=ratio, unit="percent", label="Debt payments",
        ),
        actionable=severity != "info",
        priority=60,
        generated_at=generated_at,
    )


def _cashflow_insight(forecasts: dict, fmt: Formatters) -> dict | None:
    if not forecasts:
        return None
    savings = forecasts.get("savings") or {}
    estimated = savings.get("estimated")
    if estimated is None or estimated >= 0:
        return None
    severity = (
        "critical" if estimated <= -CASHFLOW_CRITICAL_LEVEL else "warning"
    )
    return _insight(
        id="cashflow-negative-projection",
        severity=severity,
        category="cashflow",
        title="Your projected month-end cash flow is negative",
        explanation=(
            f"Based on your pace so far you would end the period "
            f"{fmt.money(abs(estimated))} below break-even ({fmt.money(estimated)}). "
            "This is an estimate, not a certainty."
        ),
        m=metric(
            kind="projected_savings", current=estimated, unit="currency",
        ),
        actionable=True,
        priority=75,
    )


def _net_worth_insight(nw: dict, fmt: Formatters) -> dict | None:
    change = nw.get("change_pct")
    if change is None:
        return None
    if change >= NETWORTH_UP_SUCCESS:
        return _insight(
            id="net-worth-up",
            severity="success",
            category="overview",
            title=f"Net worth is up {fmt.pct(change, 0)} vs last period",
            explanation=(
                f"{fmt.money(nw.get('net_worth', 0))} now, up from "
                f"{fmt.money(nw.get('previous'))} at the previous period end."
            ),
            m=metric(
                kind="net_worth", current=nw.get("net_worth", 0),
                previous=nw.get("previous"), change_pct=change, unit="currency",
            ),
            actionable=False,
            priority=50,
        )
    if change <= NETWORTH_DOWN_WARN:
        return _insight(
            id="net-worth-down",
            severity="warning",
            category="overview",
            title=f"Net worth is down {fmt.pct(abs(change), 0)} vs last period",
            explanation=(
                f"{fmt.money(nw.get('net_worth', 0))} now vs "
                f"{fmt.money(nw.get('previous'))} at the previous period end."
            ),
            m=metric(
                kind="net_worth", current=nw.get("net_worth", 0),
                previous=nw.get("previous"), change_pct=change, unit="currency",
            ),
            actionable=False,
            priority=45,
        )
    return None


def _cashflow_streak_insight(health: dict) -> dict | None:
    streak = health.get("cashflow_streak") or 0
    if streak < 2:
        return None
    return _insight(
        id="cashflow-streak",
        severity="success",
        category="overview",
        title=f"{streak} positive months in a row",
        explanation=(
            f"Income has exceeded expenses for the last {streak} completed month(s)."
        ),
        m=metric(kind="cashflow_streak", current=streak, unit="count"),
        actionable=False,
        priority=35,
    )


def _safe_to_spend_insight(safe: dict | None, fmt: Formatters) -> dict | None:
    if not safe or safe.get("status") != "ok":
        return None
    daily = safe.get("safe_to_spend_daily")
    if daily is None or daily <= 0:
        return _insight(
            id="safe-to-spend-unavailable",
            severity="warning",
            category="safe-to-spend",
            title="No discretionary money left this period",
            explanation=(
                "After upcoming obligations, planned savings and your reserve there "
                "is nothing left to spend freely."
            ),
            m=metric(kind="daily_budget", current=0.0, unit="currency"),
            actionable=True,
            priority=68,
        )
    return _insight(
        id="safe-to-spend",
        severity="info",
        category="safe-to-spend",
        title=f"Your safe daily spending is {fmt.money(daily)} per day",
        explanation=(
            f"{fmt.money(safe.get('discretionary'))} remain for the rest of the "
            f"period ({safe.get('remaining_days')} days), after commitments of "
            f"{fmt.money(safe.get('committed_total'))}."
        ),
        m=metric(kind="daily_budget", current=daily, unit="currency"),
        actionable=True,
        priority=30,
    )


def _goal_eta_insights(goals: list[dict], fmt: Formatters,
                       generated_at: str | None) -> list[dict]:
    insights: list[dict] = []
    for goal in goals:
        if not goal.get("active"):
            continue
        remaining = goal.get("remaining_amount") or 0
        contribution = goal.get("monthly_contribution")
        if remaining <= 0:
            continue
        if not contribution or contribution <= 0:
            continue
        months = ceil(remaining / contribution)
        eta = goal.get("estimated_completion_date")

        severity: str
        if goal.get("target_date") and eta:
            severity = "warning" if eta > goal["target_date"] else (
                "success" if months <= GOAL_SOON_MONTHS else "info"
            )
        elif months <= GOAL_SOON_MONTHS:
            severity = "success"
        elif months <= GOAL_FINE_MONTHS:
            severity = "info"
        else:
            severity = "warning"

        insights.append(
            _insight(
                id=f"goal-eta-{goal['id']}",
                severity=severity,
                category="goals",
                title=(
                    f"'{goal['name']}' is about {months} month{'s' if months != 1 else ''} away "
                    "at your current pace"
                ),
                explanation=(
                    f"With roughly {fmt.money(contribution)} saved monthly, the "
                    f"{fmt.money(remaining)} remaining would need about {months} "
                    "month(s)."
                    + (f" Completion is projected for {eta}." if eta else "")
                ),
                m=metric(
                    kind="months_to_goal", label=goal["name"], current=months,
                    unit="months",
                ),
                actionable=True,
                priority=55,
            )
        )
    return sorted(insights, key=lambda i: i["id"])[:2]


# -- prioritization -------------------------------------------------------------

SEVERITY_WEIGHT = {"critical": 4, "warning": 3, "success": 2, "info": 1}


def prioritize(insights: list[dict], *, max_items: int = MAX_INSIGHTS) -> list[dict]:
    """Order by severity then actionability, cap per category and total."""
    ordered = sorted(
        insights,
        key=lambda i: (
            -SEVERITY_WEIGHT.get(i.get("severity", "info"), 1),
            -bool(i.get("actionable")),
            -i.get("priority", 0),
            i.get("id", ""),
        ),
    )
    per_category: dict[str, int] = {}
    result: list[dict] = []
    for insight in ordered:
        category = insight.get("category", "overview")
        limit = MAX_PER_CATEGORY.get(category, 1)
        if per_category.get(category, 0) >= limit:
            continue
        per_category[category] = per_category.get(category, 0) + 1
        result.append(insight)
        if len(result) >= max_items:
            break
    return result


# -- overview --------------------------------------------------------------------

def greeting() -> str:
    return "Here is what I noticed this month."


def compose_overview(state: dict, fmt: Formatters, period_label: str) -> str:
    if not state.get("has_data"):
        return (
            "Your ledger has no transactions yet, so there is nothing to summarize. "
            "Record an income or expense and the assistant will start describing "
            "your money."
        )

    a = state["analytics"]
    income = a["income"]["current"]
    expense = a["expenses"]["current"]
    net = a["savings"]["current"]
    rate = a["savings"]["rate"]

    parts = [
        f"Since {period_label}, you earned {fmt.money(income)} and spent "
        f"{fmt.money(expense)}."
    ]
    if net >= 0:
        rate_text = (
            f" — {fmt.pct(rate, 0)} of your income" if rate is not None else ""
        )
        parts.append(f"You saved {fmt.money(net)}{rate_text}.")
    else:
        parts.append(f"That left you {fmt.money(abs(net))} below break-even this period.")

    nw = a.get("net_worth") or {}
    current_nw = nw.get("net_worth")
    if current_nw is not None:
        change = nw.get("change_pct")
        change_text = (
            f" ({'up' if change >= 0 else 'down'} {fmt.pct(abs(change), 1)} "
            "vs the previous period)"
            if change is not None
            else ""
        )
        text = f"Your net worth is {fmt.money(current_nw)}{change_text}."
        debts_nw = nw.get("net_worth_including_debts")
        if debts_nw is not None and debts_nw != current_nw:
            text += f" Including unpaid debts, it is {fmt.money(debts_nw)}."
        parts.append(text)

    safe = state.get("safe_to_spend")
    if safe and safe.get("status") == "ok" and safe.get("safe_to_spend_daily") is not None:
        parts.append(
            f"Right now you can safely spend about {fmt.money(safe['safe_to_spend_daily'])} "
            "per day for the rest of the period."
        )

    return " ".join(parts)


# -- structured questions -----------------------------------------------------------

def match_intent(text: str) -> str | None:
    """Best-effort deterministic mapping of a question string to an intent.

    Falls back to ``None`` when the text is not recognized; the UI offers the
    supported question chips instead of guessing.
    """
    t = (text or "").lower()
    rules = [
        ("goals_progress", ["goals progressing", "progress on", "how are my goals", "goals doing", "goal progress", "goal status"]),
        ("goal_eta", ["goal", "reach", "complete", "when will", "finish it", "fully saved"]),
        ("net_worth_contributors", ["driving", "what is behind", "why did net worth", "what made my", "drivers", "contributing to net worth", "assets vs", "liabilities"]),
        ("net_worth", ["net worth", "worth", "wealth", "richer"]),
        ("safe_to_spend", ["safe", "spend today", "spend each day", "daily", "left to spend", "afford"]),
        ("expense_increases", ["increase", "increases", "went up", "gone up", "grew", "rise", "higher"]),
        ("insights", ["pay attention", "attention to", "should i know", "any concerns", "what changed", "noticing", "anything else", "insight"]),
        ("upcoming", ["coming up", "upcoming", "due soon", "bills", "recurring", "next payment", "what is due"]),
        ("budget_status", ["budget", "on track", "track", "over budget", "under budget"]),
        ("savings", ["save", "saved", "saving", "savings"]),
        ("top_categories", ["where", "most on", "top", "category", "categories"]),
        ("spending", ["spend", "spent", "paid", "expense", "how much did"]),
    ]
    for intent, keywords in rules:
        if any(keyword in t for keyword in keywords):
            return intent
    return None


def _fact(label: str, value, display: str) -> dict:
    return {"label": label, "value": value, "display": display}


def answer_question(state: dict, intent: str, fmt: Formatters, *, goal_id: int | None = None,
                    question: str | None = None) -> dict:
    label = INTENT_LABELS.get(intent)
    question_text = question or (label["question"] if label else intent)
    if label is None:
        return {
            "intent": intent,
            "question": question_text,
            "recognized": False,
            "answer": _fallback_answer(),
            "estimate": False,
            "source": "assistant",
            "facts": [],
            "metric": None,
            "generated_at": state.get("generated_at"),
        }

    if not state.get("has_data") and intent not in {"goal_eta", "net_worth", "net_worth_contributors", "upcoming"}:
        return {
            "intent": intent,
            "question": question_text,
            "recognized": True,
            "answer": (
                "There are no recorded transactions yet, so I cannot answer that "
                "from real data."
            ),
            "estimate": False,
            "source": "ledger",
            "facts": [],
            "metric": None,
            "generated_at": state.get("generated_at"),
        }

    a = state["analytics"]
    handler = {
        "spending": _answer_spending,
        "top_categories": _answer_top_categories,
        "budget_status": _answer_budget,
        "safe_to_spend": _answer_safe_to_spend,
        "savings": _answer_savings,
        "net_worth": _answer_net_worth,
        "net_worth_contributors": _answer_net_worth_contributors,
        "expense_increases": _answer_expense_increases,
        "insights": _answer_insights,
        "upcoming": _answer_upcoming,
        "goals_progress": _answer_goals_progress,
        "goal_eta": _answer_goal_eta,
    }[intent]

    result = handler(state, fmt, goal_id=goal_id, a=a)
    result["intent"] = intent
    result["question"] = question_text
    result["generated_at"] = state.get("generated_at")
    return result


def _fallback_answer() -> str:
    return (
        "I answer structured questions about your recorded finances. "
        "Try: " + " · ".join(q["question"] for q in QUESTIONS) + "."
    )


def _answer_spending(state, fmt, *, a, goal_id=None) -> dict:
    cur = a["expenses"]["current"]
    prev = a["expenses"]["previous"]
    change = a["expenses"]["change_pct"]
    facts = [
        _fact("Spent this period", cur, fmt.money(cur)),
        _fact("Last period", prev, fmt.money(prev)),
    ]
    if change is not None:
        facts.append(_fact("Change", change, fmt.pct(change, 1)))
    answer = f"You spent {fmt.money(cur)} this period."
    if change is not None:
        direction = "+" if change > 0 else ""
        answer += f" That is {direction}{fmt.pct(change, 1)} vs last period."
    return {
        "recognized": True,
        "answer": answer,
        "estimate": False,
        "source": "ledger",
        "facts": facts,
        "metric": metric(kind="total_spent", current=cur, previous=prev,
                         change_pct=change),
    }


def _answer_top_categories(state, fmt, *, a, goal_id=None) -> dict:
    categories = a.get("categories") or []
    if not categories:
        return {
            "recognized": True,
            "answer": "No expenses were recorded this period.",
            "estimate": False,
            "source": "ledger",
            "facts": [],
            "metric": None,
        }
    top = categories[0]
    name = top.get("category_name") or "uncategorized"
    facts = [
        _fact(name, top["amount"], fmt.money(top["amount"])),
    ]
    for item in categories[1:4]:
        facts.append(_fact(item.get("category_name") or "?", item["amount"],
                           fmt.money(item["amount"])))
    share = top.get("share_pct")
    share_text = f", or {fmt.pct(share, 0)} of everything" if share is not None else ""
    answer = f"Your biggest expense is {name}: {fmt.money(top['amount'])}{share_text}."
    if len(categories) > 1:
        rest = ", ".join(f"{fmt.money(c['amount'])} on {c.get('category_name') or '?'}"
                         for c in categories[1:4])
        answer += f" You also spent {rest}."
    return {
        "recognized": True,
        "answer": answer,
        "estimate": False,
        "source": "ledger",
        "facts": facts,
        "metric": metric(kind="top_category", label=name, current=top["amount"],
                         change_pct=top.get("share_pct"), unit="percent"),
    }


def _answer_budget(state, fmt, *, a, goal_id=None) -> dict:
    budget = a.get("budget") or {}
    totals = budget.get("totals") or {}
    planned = totals.get("planned") or 0
    actual = totals.get("actual") or 0
    pct_used = totals.get("pct_used")
    over = totals.get("over_budget")

    projection = state.get("projection") or {}
    projected_total = None
    if projection and (projection.get("elapsed") or 0) > 0:
        projected_total = straight_line_projection(actual, projection["elapsed"],
                                                   projection["total"])

    facts = [
        _fact("Budgeted", planned, fmt.money(planned)),
        _fact("Spent", actual, fmt.money(actual)),
    ]
    if pct_used is not None:
        facts.append(_fact("Budget used", pct_used, fmt.pct(pct_used, 0)))
    if projected_total is not None:
        facts.append(_fact("Projected end", projected_total, fmt.money(projected_total)))

    if planned <= 0:
        answer = (
            "You have no category budget set this period, so there is nothing to "
            "track against."
        )
        source = "ledger"
    elif over:
        answer = f"You are over budget: {fmt.money(actual)} spent against {fmt.money(planned)} planned."
        source = "ledger"
    elif pct_used is not None and pct_used >= BUDGET_WARN_PCT:
        answer = (
            f"You are close to your budget ceiling: {fmt.pct(pct_used, 0)} used "
            f"({fmt.money(actual)} of {fmt.money(planned)})."
        )
        source = "ledger"
    elif projected_total is not None and projected_total > planned:
        answer = (
            f"At your current pace you are projected to exceed the {fmt.money(planned)} "
            f"budget by about {fmt.money(projected_total - planned)}."
        )
        source = "estimate"
    else:
        answer = (
            f"You are on track: {fmt.money(actual)} spent of {fmt.money(planned)} "
            f"planned ({fmt.pct(pct_used, 0) if pct_used is not None else '0'}% used)."
        )
        source = "ledger"

    return {
        "recognized": True,
        "answer": answer,
        "estimate": source == "estimate",
        "source": source,
        "facts": facts,
        "metric": metric(kind="budget_status", current=actual, previous=planned,
                         change_pct=pct_used, unit="percent"),
    }


def _answer_safe_to_spend(state, fmt, *, a, goal_id=None) -> dict:
    safe = state.get("safe_to_spend")
    if not safe or safe.get("status") != "ok":
        return {
            "recognized": True,
            "answer": (
                "There is not enough history to estimate a safe amount yet; "
                "record an income or expense first."
            ),
            "estimate": False,
            "source": "ledger",
            "facts": [],
            "metric": None,
        }
    facts = [
        _fact("Available", safe.get("available_money"), fmt.money(safe.get("available_money"))),
        _fact("Obligations", safe.get("obligations_total"), fmt.money(safe.get("obligations_total"))),
        _fact("Planned savings", safe.get("planned_savings"), fmt.money(safe.get("planned_savings"))),
        _fact("Reserve", safe.get("reserve_amount"), fmt.money(safe.get("reserve_amount"))),
        _fact("Discretionary", safe.get("discretionary"), fmt.money(safe.get("discretionary"))),
        _fact("Days left", safe.get("remaining_days"), str(safe.get("remaining_days"))),
        _fact("Daily budget", safe.get("safe_to_spend_daily"), fmt.money(safe.get("safe_to_spend_daily"))),
    ]
    answer = (
        f"You can safely spend about {fmt.money(safe['safe_to_spend_daily'])} per day "
        f"for the next {safe['remaining_days']} days — after obligations, planned "
        "savings and reserve."
    )
    if safe.get("safe_to_spend_daily") == 0:
        answer = "Nothing is left to spend freely this period after your commitments."
    return {
        "recognized": True,
        "answer": answer,
        "estimate": bool(safe.get("is_estimate")),
        "source": "estimate" if safe.get("is_estimate") else "ledger",
        "facts": facts,
        "metric": metric(kind="daily_budget", current=safe.get("safe_to_spend_daily"),
                         unit="currency"),
    }


def _answer_savings(state, fmt, *, a, goal_id=None) -> dict:
    savings = a["savings"]
    rate = savings.get("rate")
    facts = [
        _fact("Saved this period", savings["current"], fmt.money(savings["current"])),
        _fact("Last period", savings["previous"], fmt.money(savings["previous"])),
    ]
    if rate is not None:
        facts.append(_fact("Savings rate", rate, fmt.pct(rate, 1)))
    if savings.get("historical_rate") is not None:
        facts.append(_fact("Historic rate", savings["historical_rate"],
                           fmt.pct(savings["historical_rate"], 1)))

    net = savings["current"]
    if net >= 0:
        rate_text = f" ({fmt.pct(rate, 1)} of income)" if rate is not None else ""
        answer = f"You saved {fmt.money(net)} this period{rate_text}."
    else:
        answer = f"You spent {fmt.money(abs(net))} more than you earned this period."
    change = savings.get("change_pct")
    if change is not None and abs(change) >= 0.5:
        answer += f" That is {'up' if change > 0 else 'down'} {fmt.pct(abs(change), 1)} vs last period."
    return {
        "recognized": True,
        "answer": answer,
        "estimate": False,
        "source": "ledger",
        "facts": facts,
        "metric": metric(kind="savings", current=net, previous=savings["previous"],
                         change_pct=change),
    }


def _answer_net_worth(state, fmt, *, a, goal_id=None) -> dict:
    nw = a.get("net_worth") or {}
    current = nw.get("net_worth", 0)
    previous = nw.get("previous")
    change = nw.get("change_pct")
    facts = [
        _fact("Net worth", current, fmt.money(current)),
        _fact("Assets", nw.get("assets"), fmt.money(nw.get("assets"))),
        _fact("Liabilities", nw.get("liabilities"), fmt.money(nw.get("liabilities"))),
    ]
    if previous is not None:
        facts.append(_fact("Last period", previous, fmt.money(previous)))
    if change is not None:
        facts.append(_fact("Change", change, fmt.pct(change, 1)))
    answer = f"Your net worth is {fmt.money(current)}."
    if change is not None:
        answer += f" That is {'up' if change >= 0 else 'down'} {fmt.pct(abs(change), 1)} vs the previous period."
    return {
        "recognized": True,
        "answer": answer,
        "estimate": False,
        "source": "ledger",
        "facts": facts,
        "metric": metric(kind="net_worth", current=current, previous=previous,
                         change_pct=change),
    }


def _answer_expense_increases(state, fmt, *, a, goal_id=None) -> dict:
    categories = a.get("categories") or []
    increased = [c for c in categories if (c.get("change_pct") or 0) > 0]
    increased.sort(key=lambda c: -c["change_pct"])
    if not increased:
        return {
            "recognized": True,
            "answer": "No category cost more this period than last.",
            "estimate": False,
            "source": "ledger",
            "facts": [],
            "metric": metric(kind="category_change", unit="percent"),
        }
    facts = [
        _fact(c.get("category_name") or "?", c["change_pct"],
              f"{fmt.pct(c['change_pct'], 1)}")
        for c in increased[:5]
    ]
    names = ", ".join(
        f"{c.get('category_name') or '?'} ({fmt.pct(c['change_pct'], 0)})"
        for c in increased[:3]
    )
    answer = f"These categories are up this period: {names}."
    return {
        "recognized": True,
        "answer": answer,
        "estimate": False,
        "source": "ledger",
        "facts": facts,
        "metric": metric(kind="category_change", unit="percent"),
    }


def _answer_goal_eta(state, fmt, *, a, goal_id=None) -> dict:
    goals = [g for g in (state.get("goals") or []) if g.get("active")]
    if goal_id is not None:
        selected = next((g for g in goals if g["id"] == goal_id), None)
    else:
        selected = next(
            (g for g in goals if (g.get("monthly_contribution") or 0) > 0
             and (g.get("remaining_amount") or 0) > 0), None
        )

    if not selected:
        supported = ", ".join(g["name"] for g in goals) or "none"
        return {
            "recognized": True,
            "answer": f"No goal with a funding pace is active yet ({supported}).",
            "estimate": True,
            "source": "plan",
            "facts": [],
            "metric": None,
        }

    remaining = selected.get("remaining_amount") or 0
    contribution = selected.get("monthly_contribution") or 0
    months = ceil(remaining / contribution) if contribution > 0 else None
    eta = selected.get("estimated_completion_date")

    facts = [
        _fact("Remaining", remaining, fmt.money(remaining)),
        _fact("Monthly pace", contribution, fmt.money(contribution)),
    ]
    if months is not None:
        facts.append(_fact("Months away", months, f"{months}"))
    if eta:
        facts.append(_fact("Estimated completion", str(eta), str(eta)))
    else:
        months_units = f"about {months} month{'s' if months != 1 else ''}"
        if months is not None:
            facts.append(_fact("Estimated completion", None, months_units))

    answer = (
        f"'{selected['name']}' is about {months} month{'s' if months != 1 else ''} "
        "away at your current pace."
        if months is not None
        else f"'{selected['name']}' needs {fmt.money(remaining)} more; "
        "there is no measured funding pace yet."
    )
    if eta:
        answer += f" That puts completion around {eta}."
    return {
        "recognized": True,
        "answer": answer,
        "estimate": True,
        "source": "estimate" if months is not None else "plan",
        "facts": facts,
        "metric": metric(kind="months_to_goal", label=selected["name"], current=months,
                         unit="months"),
    }


def _answer_net_worth_contributors(state, fmt, *, a, goal_id=None) -> dict:
    nw = a["net_worth"]
    assets = nw["assets"]
    liabilities = nw["liabilities"]
    net = nw["net_worth"]
    previous = nw["previous"]
    change = nw["change_pct"]

    facts = [
        _fact("Assets", assets, fmt.money(assets)),
        _fact("Liabilities", liabilities, fmt.money(liabilities)),
        _fact("Net worth", net, fmt.money(net)),
        _fact("Previous period", previous, fmt.money(previous)),
    ]
    if change is not None:
        facts.append(_fact("Change", change, fmt.pct(change, 1)))

    direction = "up" if (change or 0) > 0 else ("down" if (change or 0) < 0 else "flat")
    if change is None or change == 0:
        answer = (
            f"Your net worth is {fmt.money(net)} — steady since last period. "
            f"Assets are {fmt.money(assets)} and liabilities are "
            f"{fmt.money(liabilities)}."
        )
    else:
        sign = "+" if change > 0 else ""
        answer = (
            f"Your net worth is {fmt.money(net)}, {sign}{fmt.pct(change, 1)} {direction} "
            f"since last period. Assets are {fmt.money(assets)} and liabilities are "
            f"{fmt.money(liabilities)}."
        )
    return {
        "recognized": True,
        "answer": answer,
        "estimate": False,
        "source": "ledger",
        "facts": facts,
        "metric": metric(kind="net_worth", current=net, previous=previous,
                         change_pct=change),
    }


def _answer_insights(state, fmt, *, a, goal_id=None) -> dict:
    insights = state.get("insights") or []
    top = insights[:3]
    if not top:
        return {
            "recognized": True,
            "answer": "Nothing currently needs your attention.",
            "estimate": False,
            "source": "ledger",
            "facts": [],
            "metric": None,
        }
    facts = [
        _fact(f"{i + 1}. {item['title']}", None, item["explanation"])
        for i, item in enumerate(top)
    ]
    bullets = "\n".join(
        f"• {item['title']}" for item in top
    )
    return {
        "recognized": True,
        "answer": f"Things worth paying attention to:\n{bullets}",
        "estimate": False,
        "source": "ledger",
        "facts": facts,
        "metric": metric(kind="insights", label=f"{len(top)} items", current=len(top),
                         unit="count"),
    }


def _answer_upcoming(state, fmt, *, a, goal_id=None) -> dict:
    upcoming = (state.get("upcoming") or {}).get("occurrences") or []
    due = [item for item in upcoming if not item.get("overdue")]
    total = sum(float(item["amount"]) for item in due)
    overdue = sum(float(item["amount"]) for item in upcoming if item.get("overdue"))
    next_item = sorted(upcoming, key=lambda item: item["due_date"])[0] if upcoming else None

    facts = [
        _fact("Upcoming payments", len(upcoming), f"{len(upcoming)}"),
        _fact("Due in the next 15 days", total, fmt.money(total)),
    ]
    if overdue > 0:
        facts.append(_fact("Overdue", len([i for i in upcoming if i["overdue"]]),
                           f"{len([i for i in upcoming if i['overdue']])}"))
    if next_item:
        name = next_item["description"] or next_item["category_name"] or "payment"
        facts.append(_fact("Next up", str(next_item["due_date"]),
                           f"{name} on {next_item['due_date']}"))

    if not upcoming:
        answer = "No recurring payments are scheduled in the next 15 days."
    else:
        heading = (
            f"You have {len(upcoming)} recurring {'payment' if len(upcoming) == 1 else 'payments'} "
            f"scheduled in the next 15 days totalling {fmt.money(total)}."
        )
        names = [item["description"] or item.get("category_name") or "?" for item in due[:3]]
        answer = heading
        if names:
            answer += " Next up: " + ", ".join(names) + "."
    return {
        "recognized": True,
        "answer": answer,
        "estimate": True,
        "source": "plan",
        "facts": facts,
        "metric": metric(kind="upcoming_total", current=total, unit="currency") if total else None,
    }


def _answer_goals_progress(state, fmt, *, a, goal_id=None) -> dict:
    goals = [g for g in (state.get("goals") or []) if g.get("active")]
    if not goals:
        return {
            "recognized": True,
            "answer": "You have no active goals yet.",
            "estimate": False,
            "source": "plan",
            "facts": [],
            "metric": None,
        }
    facts = []
    lines = []
    for goal in goals:
        target = float(goal.get("target_amount") or 0)
        current = float(goal.get("current_amount") or 0)
        remaining = float(goal.get("remaining_amount") or 0)
        funded = (current / target * 100) if target else 0.0
        pace = float(goal.get("monthly_contribution") or 0)
        label = f"{goal['name']} ({funded:.0f}% funded)"
        if pace > 0 and remaining > 0:
            months = ceil(remaining / pace)
            detail = f"{fmt.money(remaining)} left · {months} month{'s' if months != 1 else ''} at current pace"
        elif pace > 0:
            detail = f"fully funded at {fmt.money(pace)}/month"
        else:
            detail = f"no funding pace set yet"
        facts.append(_fact(label, round(funded, 1), detail))
        lines.append(f"{goal['name']} is {funded:.0f}% funded")
    answer = "\n".join(f"• {line}" for line in lines) + ". "
    return {
        "recognized": True,
        "answer": answer,
        "estimate": True,
        "source": "plan",
        "facts": facts,
        "metric": metric(kind="goals_progress", label=f"{len(goals)} goals",
                         current=None, unit="percent"),
    }