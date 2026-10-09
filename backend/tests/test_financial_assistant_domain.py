"""Pure tests for the Financial Assistant insight engine + Q&A.

No database: every scenario feeds an explicit ``state`` payload (the same
shape the service assembles from the analytics engine) so thresholds and
prioritization are verified deterministically.
"""

from __future__ import annotations

from datetime import date

from app.domain.financial_assistant import (
    MAX_INSIGHTS,
    Formatters,
    answer_question,
    compose_overview,
    generate_insights,
    greeting,
    match_intent,
    prioritize,
)


def money(value) -> str:
    return f"${float(value):,.2f}"


def pct(value, digits: int) -> str:
    return f"{float(value or 0):,.{digits}f}%"


FMT = Formatters(money=money, pct=pct)


def analytics_summary(**overrides):
    summary = {
        "income": {"current": 3000.0, "previous": 2500.0, "change_pct": 20.0, "trend": "up"},
        "expenses": {"current": 650.0, "previous": 300.0, "change_pct": 116.7, "trend": "up"},
        "savings": {
            "current": 2350.0,
            "previous": 2200.0,
            "change_pct": 6.8,
            "rate": 78.3,
            "rate_status": "positive",
            "historical_rate": 88.0,
        },
        "categories": [
            {"category_name": "Food", "amount": 500.0, "share_pct": 60.0, "change_pct": 20.0},
            {"category_name": "Transport", "amount": 150.0, "share_pct": 20.0, "change_pct": 50.0},
        ],
        "net_worth": {
            "assets": 5550.0,
            "liabilities": 200.0,
            "net_worth": 5350.0,
            "net_worth_including_debts": 5350.0,
            "previous": 3000.0,
            "change_pct": 78.3,
        },
        "budget": {
            "totals": {
                "planned": 600.0,
                "actual": 650.0,
                "pct_used": 108.3,
                "over_budget": True,
                "remaining": -50.0,
            },
            "items": [
                {
                    "category_name": "Food",
                    "planned_amount": 400.0,
                    "actual_amount": 500.0,
                    "pct_used": 125.0,
                    "over_budget": True,
                    "status": "over",
                }
            ],
        },
        "history": [
            {"closed": True, "income": 2500.0, "expense": 300.0, "net": 2200.0, "savings_rate": 88.0}
        ],
        "forecasts": {"savings": {"actual": 2350.0, "estimated": 2000.0, "is_estimate": True}},
        "health": {"cashflow_streak": 2},
    }
    summary.update(overrides)
    return summary


def make_state(**overrides):
    state = {
        "has_data": True,
        "generated_at": "2026-10-08T00:00:00+00:00",
        "currency": "USD",
        "period": {
            "period_start": date(2026, 10, 1),
            "period_end": date(2026, 10, 31),
        },
        "analytics": analytics_summary(),
        "safe_to_spend": {
            "status": "ok",
            "is_estimate": True,
            "available_money": 5000.0,
            "obligations": [
                {"kind": "recurring", "amount": 150.0},
                {"kind": "debt", "amount": 120.0},
            ],
            "obligations_total": 270.0,
            "planned_savings": 600.0,
            "reserve_amount": 300.0,
            "committed_total": 1170.0,
            "discretionary": 250.0,
            "remaining_days": 20,
            "safe_to_spend_daily": 12.5,
        },
        "goals": [],
        "debts": [],
        "income_basis": 3000.0,
        "monthly_recurring": 150.0,
        "monthly_debt_minimums": 120.0,
        "projection": {"elapsed": 8, "total": 31},
    }
    state.update(overrides)
    return state


def insight_ids(items) -> list[str]:
    return [item["id"] for item in items]


def severity_by_id(items) -> dict[str, str]:
    return {item["id"]: item["severity"] for item in items}


# -- no-data ------------------------------------------------------------------


def test_no_data_state_yields_single_insight():
    state = make_state(
        has_data=False,
        analytics=analytics_summary(
            income={"current": 0.0, "previous": 0.0, "change_pct": None, "trend": "none"},
            expenses={"current": 0.0, "previous": 0.0, "change_pct": None, "trend": "none"},
            savings={"current": 0.0, "previous": 0.0, "change_pct": None,
                     "rate": None, "rate_status": "insufficient", "historical_rate": None},
            categories=[],
            net_worth={"assets": 0.0, "liabilities": 0.0, "net_worth": 0.0,
                       "net_worth_including_debts": 0.0, "previous": None, "change_pct": None},
            budget={"totals": {}, "items": []},
            history=[],
            forecasts={},
            health={"cashflow_streak": 0},
        ),
        goal_id=None,
    )
    insights = generate_insights(state, FMT)
    assert insight_ids(insights) == ["no-data"]
    assert insights[0]["severity"] == "info"
    assert "ledger" in insights[0]["explanation"].lower()


def test_no_data_overview_and_answer():
    state = make_state(
        has_data=False,
        analytics=analytics_summary(
            income={"current": 0.0, "previous": 0.0, "change_pct": None, "trend": "none"},
            expenses={"current": 0.0, "previous": 0.0, "change_pct": None, "trend": "none"},
            savings={"current": 0.0, "previous": 0.0, "change_pct": None,
                     "rate": None, "rate_status": "insufficient", "historical_rate": None},
            categories=[],
            net_worth={"assets": 0.0, "liabilities": 0.0, "net_worth": 0.0,
                       "net_worth_including_debts": 0.0, "previous": None, "change_pct": None},
            budget={"totals": {}, "items": []},
            history=[],
            forecasts={},
            health={"cashflow_streak": 0},
        ),
        safe_to_spend=None,
        income_basis=None,
        monthly_recurring=0.0,
        monthly_debt_minimums=0.0,
    )
    overview = compose_overview(state, FMT, "Sep 1 – Sep 30, 2026")
    assert "nothing to summarize" in overview

    result = answer_question(state, "budget_status", FMT, question="Am I on track with my budget?")
    assert result["recognized"] is True
    assert result["source"] == "ledger"
    assert "no recorded transactions" in result["answer"].lower()


# -- insights ----------------------------------------------------------------


def test_overlapping_budget_overspent_is_critical_and_first():
    state = make_state()
    insights = prioritize(generate_insights(state, FMT))
    ids = insight_ids(insights)
    assert "budget-over-food" in ids
    assert severity_by_id(insights)["budget-over-food"] == "critical"
    # severity sorting puts the most urgent insight first, never hidden below info
    assert insights[0]["severity"] == "critical"
    assert insights[0]["id"] == "budget-over-food"


def test_projection_insight_for_close_budget():
    state = make_state(
        projection={"elapsed": 8, "total": 31},
        analytics=analytics_summary(
            budget={
                "totals": {"planned": 600.0, "actual": 300.0, "pct_used": 50.0,
                           "over_budget": False, "remaining": 300.0},
                "items": [
                    {"category_name": "Food", "planned_amount": 400.0, "actual_amount": 300.0,
                     "pct_used": 75.0, "over_budget": False, "status": "on_track"},
                ],
            },
        ),
    )
    ids = insight_ids(generate_insights(state, FMT))
    assert "budget-projected-food" in ids


def test_savings_rate_improvement_is_success():
    state = make_state(
        analytics=analytics_summary(
            savings={
                "current": 2800.0,
                "previous": 2000.0,
                "change_pct": 40.0,
                "rate": 90.0,
                "rate_status": "positive",
                "historical_rate": 60.0,
            },
            history=[
                {"closed": True, "income": 2500.0, "expense": 1000.0, "net": 1500.0,
                 "savings_rate": 60.0},
                {"closed": False, "income": 3000.0, "expense": 200.0, "net": 2800.0,
                 "savings_rate": 90.0},
            ],
        ),
    )
    insights = generate_insights(state, FMT)
    assert severity_by_id(insights).get("savings-rate-improved") == "success"


def test_savings_rate_declined_is_warning():
    state = make_state(
        analytics=analytics_summary(
            savings={
                "current": 200.0,
                "previous": 2200.0,
                "change_pct": -90.0,
                "rate": 6.7,
                "rate_status": "neutral",
                "historical_rate": 88.0,
            },
            categories=[],
            history=[
                {"closed": True, "income": 2500.0, "expense": 300.0, "net": 2200.0,
                 "savings_rate": 88.0},
                {"closed": False, "income": 3000.0, "expense": 2800.0, "net": 200.0,
                 "savings_rate": 6.7},
            ],
        ),
    )
    insights = generate_insights(state, FMT)
    assert severity_by_id(insights).get("savings-rate-declined") == "warning"


def test_negative_savings_critical():
    state = make_state(
        analytics=analytics_summary(
            savings={
                "current": -500.0,
                "previous": 2200.0,
                "change_pct": -122.7,
                "rate": -25.0,
                "rate_status": "negative",
                "historical_rate": 88.0,
            },
            categories=[],
            budget={"totals": {"planned": 0.0, "actual": 0.0, "pct_used": 0.0,
                               "over_budget": False, "remaining": 0.0}, "items": []},
        ),
        safe_to_spend=None,
        monthly_recurring=0.0,
        monthly_debt_minimums=0.0,
    )
    insights = generate_insights(state, FMT)
    assert insights[0]["id"] == "savings-negative"
    assert insights[0]["severity"] == "critical"


def test_increased_recurring_expenses_warns_above_half_of_income():
    state = make_state(monthly_recurring=1500.0, income_basis=3000.0)
    insights = generate_insights(state, FMT)
    assert severity_by_id(insights).get("recurring-income-share") == "warning"
    explanation = next(i for i in insights if i["id"] == "recurring-income-share")["explanation"]
    assert "$1,500.00" in explanation


def test_debt_ratio_warning_and_critical():
    state = make_state(monthly_debt_minimums=900.0, income_basis=3000.0)
    insights = generate_insights(state, FMT)
    assert severity_by_id(insights).get("debt-income-share") == "warning"

    state = make_state(monthly_debt_minimums=1500.0, income_basis=3000.0)
    insights = generate_insights(state, FMT)
    assert severity_by_id(insights).get("debt-income-share") == "critical"


def test_cashflow_negative_projection():
    state = make_state(
        analytics=analytics_summary(
            forecasts={"savings": {"actual": -400.0, "estimated": -1500.0, "is_estimate": True}}
        ),
    )
    insights = generate_insights(state, FMT)
    assert severity_by_id(insights).get("cashflow-negative-projection") == "critical"
    item = next(i for i in insights if i["id"] == "cashflow-negative-projection")
    assert "estimate" in item["explanation"].lower()


def test_net_worth_insights():
    state = make_state()
    insights = generate_insights(state, FMT)
    assert severity_by_id(insights).get("net-worth-up") == "success"

    state = make_state(
        analytics=analytics_summary(
            net_worth={"assets": 2800.0, "liabilities": 200.0, "net_worth": 2600.0,
                       "net_worth_including_debts": 2600.0, "previous": 3000.0,
                       "change_pct": -13.3},
        )
    )
    insights = generate_insights(state, FMT)
    assert severity_by_id(insights).get("net-worth-down") == "warning"


def test_cashflow_streak_success():
    state = make_state(
        analytics=analytics_summary(health={"cashflow_streak": 3}),
    )
    insights = generate_insights(state, FMT)
    assert severity_by_id(insights).get("cashflow-streak") == "success"


def test_safe_to_spend_insight_and_zero_daily():
    insights = generate_insights(make_state(), FMT)
    assert severity_by_id(insights).get("safe-to-spend") == "info"

    state = make_state(safe_to_spend=dict(make_state()["safe_to_spend"], safe_to_spend_daily=0.0))
    insights = generate_insights(state, FMT)
    assert severity_by_id(insights).get("safe-to-spend-unavailable") == "warning"


def test_goal_eta_variants():
    def goal(months, target_date=None, eta=None):
        return {
            "id": 1,
            "name": "New Car",
            "active": True,
            "remaining_amount": months * 500.0,
            "monthly_contribution": 500.0,
            "estimated_completion_date": eta,
            "target_date": target_date,
        }

    # far away -> warning
    state = make_state(goals=[goal(6, None, None)])
    insights = generate_insights(state, FMT)
    assert severity_by_id(insights).get("goal-eta-1") == "success"

    state = make_state(goals=[goal(14, None, None)])
    insights = generate_insights(state, FMT)
    assert severity_by_id(insights).get("goal-eta-1") == "warning"

    # past target date at current pace -> warning
    state = make_state(goals=[goal(8, date(2026, 6, 30), date(2026, 12, 1))])
    insights = generate_insights(state, FMT)
    assert severity_by_id(insights).get("goal-eta-1") == "warning"


def test_no_goal_spam_single_per_category_and_max_cap():
    goals = [
        {
            "id": i,
            "name": f"Goal {i}",
            "active": True,
            "remaining_amount": 3000.0 * i,
            "monthly_contribution": 500.0,
            "estimated_completion_date": None,
            "target_date": None,
        }
        for i in range(1, 5)
    ]
    state = make_state(goals=goals)
    insights = prioritize(generate_insights(state, FMT))
    assert len([i for i in insights if i["category"] == "goals"]) <= 1
    assert len(insights) <= MAX_INSIGHTS


# -- prioritization ------------------------------------------------------------


def test_prioritize_severity_and_actionable_then_priority():
    critical = {
        "id": "a", "severity": "critical", "category": "alert",
        "title": "", "explanation": "", "actionable": True, "priority": 99,
    }
    critical_low = {
        "id": "b", "severity": "critical", "category": "notice",
        "title": "", "explanation": "", "actionable": False, "priority": 95,
    }
    warning = {
        "id": "c", "severity": "warning", "category": "heads_up",
        "title": "", "explanation": "", "actionable": True, "priority": 90,
    }
    ordered = prioritize([warning, critical_low, critical])
    assert [i["id"] for i in ordered] == ["a", "b", "c"]


def test_prioritize_respects_per_category_caps():
    def make_item(category, idx):
        return {
            "id": f"{category}-{idx}", "severity": "critical", "category": category,
            "title": "", "explanation": "", "actionable": True, "priority": 100 - idx,
        }

    insights = [
        make_item("spending", 1),
        make_item("spending", 2),
        make_item("spending", 3),
        make_item("budget", 1),
        make_item("budget", 2),
        make_item("budget", 3),
    ]
    ordered = prioritize(insights)
    ids = [i["id"] for i in ordered]
    assert len([i for i in ids if i.startswith("spending")]) == 2
    assert len([i for i in ids if i.startswith("budget")]) == 2


# -- structured questions -------------------------------------------------------


def test_all_structured_questions_are_supported():
    state = make_state()
    for intent in ("spending", "top_categories", "budget_status", "safe_to_spend",
                   "savings", "net_worth", "expense_increases", "goal_eta"):
        result = answer_question(state, intent, FMT, question=f"?{intent}")
        assert result["intent"] == intent
        assert result["recognized"] is True
        assert result["answer"]
        assert isinstance(result["facts"], list)


def test_savings_answer_includes_amount_and_rate():
    result = answer_question(make_state(), "savings", FMT, question="How much did I save?")
    assert "$2,350.00" in result["answer"]
    assert result["source"] == "ledger"
    assert result["estimate"] is False


def test_expense_increases_lists_only_grown_categories():
    result = answer_question(make_state(), "expense_increases", FMT, question="Which increased?")
    assert "Food (20%)" in result["answer"]
    assert "Transport (50%)" in result["answer"]
    assert result["source"] == "ledger"


def test_budget_status_over_ledger_vs_projection_estimate():
    over = answer_question(make_state(), "budget_status", FMT, question="Am I on budget?")
    assert over["source"] == "ledger"
    assert "over budget" in over["answer"].lower()

    projected = answer_question(
        make_state(
            projection={"elapsed": 8, "total": 31},
            analytics=analytics_summary(
                budget={
                    "totals": {"planned": 1000.0, "actual": 500.0, "pct_used": 50.0,
                               "over_budget": False, "remaining": 500.0},
                    "items": [],
                },
            ),
        ),
        "budget_status",
        FMT,
        question="Am I on budget?",
    )
    assert projected["source"] == "estimate"
    assert projected["estimate"] is True
    assert "projected" in projected["answer"].lower()


def test_safe_to_spend_answer_from_plan_estimates():
    result = answer_question(make_state(), "safe_to_spend", FMT, question="Can I spend?")
    assert result["source"] == "estimate"
    assert result["estimate"] is True
    assert "$12.50" in result["answer"]


def test_unrecognized_intent_falls_back_to_supported_questions():
    result = answer_question(make_state(), "unknown", FMT, question="What is the meaning?")
    assert result["recognized"] is False
    assert "Try:" in result["answer"]


def test_goal_eta_answer_uses_given_goal_id():
    goal_a = {
        "id": 7, "name": "Target A", "active": True, "remaining_amount": 500.0,
        "monthly_contribution": 100.0, "estimated_completion_date": None, "target_date": None,
    }
    goal_b = {
        "id": 9, "name": "Target B", "active": True, "remaining_amount": 1200.0,
        "monthly_contribution": 100.0, "estimated_completion_date": None, "target_date": None,
    }
    state = make_state(goals=[goal_a, goal_b])
    result = answer_question(state, "goal_eta", FMT, goal_id=9, question="When will I reach my goal?")
    assert "Target B" in result["answer"]
    assert "12 months" in result["answer"]
    assert result["estimate"] is True
    assert result["source"] == "estimate"


# -- intent matching --------------------------------------------------------


def test_match_intent_recognizes_all_canonical_questions():
    cases = {
        "How much did I spend this month?": "spending",
        "Where am I spending the most?": "top_categories",
        "Am I on track with my budget?": "budget_status",
        "How much can I safely spend today?": "safe_to_spend",
        "How much did I save?": "savings",
        "How is my net worth changing?": "net_worth",
        "Which expenses increased?": "expense_increases",
        "When will I reach my goal?": "goal_eta",
    }
    for question, expected in cases.items():
        assert match_intent(question) == expected, question


def test_match_intent_unknown_returns_none():
    assert match_intent("What is the meaning of life, the universe and everything?") is None
    assert match_intent("") is None
    assert match_intent("zzz") is None


def test_match_intent_explicit_intent_wins_in_service_flow():
    # "budget" mentions in a spending question should not override an explicit intent.
    assert match_intent("budget") == "budget_status"
    assert match_intent("spend") == "spending"


# -- overview -----------------------------------------------------------------


def test_greeting_and_overview_facts():
    assert greeting() == "Here is what I noticed this month."
    overview = compose_overview(make_state(), FMT, "Sep 1 – Sep 30, 2026")
    assert "Since Sep 1 – Sep 30, 2026, you earned $3,000.00 and spent $650.00." in overview
    assert "saved $2,350.00" in overview
    assert "78.3%" in overview
    assert "net worth is $5,350.00" in overview
    assert "safely spend about $12.50" in overview


def test_overview_negative_net_wording():
    state = make_state(
        analytics=analytics_summary(savings={"current": -50.0, "previous": -20.0,
                                             "change_pct": -150.0, "rate": -1.7,
                                             "rate_status": "negative", "historical_rate": 5.0})
    )
    overview = compose_overview(state, FMT, "Sep 1 – Sep 30, 2026")
    assert "$50.00 below break-even" in overview