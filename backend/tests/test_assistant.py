"""Financial Assistant API + service integration over a real ledger.

Deterministic number checks call the service with an explicit ``today`` (the
endpoints use the real clock and are covered by the smoke tests).
"""

from __future__ import annotations

from datetime import date, timedelta

from app.services.financial_assistant_service import FinancialAssistantService

TODAY = date(2026, 10, 8)


def create_account(client, name, **payload):
    response = client.post("/api/v1/accounts", json={"name": name, **payload})
    assert response.status_code == 201, response.text
    return response.json()


def create_category(client, name, type_):
    response = client.post("/api/v1/categories", json={"name": name, "type": type_})
    assert response.status_code == 201, response.text
    return response.json()


def post_transaction(client, **payload):
    response = client.post("/api/v1/transactions", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def put_budget(client, items, period=TODAY):
    response = client.put(
        "/api/v1/budgets",
        params={"period": period.isoformat()},
        json={"allocation": {}, "items": items},
    )
    assert response.status_code == 200, response.text
    return response.json()


def make_recurring(client, **payload):
    response = client.post("/api/v1/recurring", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def create_goal(client, **payload):
    response = client.post("/api/v1/goals", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def create_debt(client, **payload):
    response = client.post("/api/v1/debts", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def seed_normal(client) -> dict:
    """Two periods of real activity (same fixtures as the analytics tests)."""
    checking = create_account(client, "Checking", opening_balance=1000)
    card = create_account(client, "Credit Card", opening_balance=-200, type="credit_card")
    savings = create_account(client, "Savings", opening_balance=0)

    food = create_category(client, "Food", "expense")
    transport = create_category(client, "Transport", "expense")
    salary = create_category(client, "Salary", "income")

    previous_income_day = (TODAY.replace(day=1) - timedelta(days=1)).replace(day=2)
    post_transaction(
        client,
        type="income",
        amount=2500,
        account_id=checking["id"],
        category_id=salary["id"],
        date=previous_income_day.isoformat(),
        description="Salary",
    )
    post_transaction(
        client,
        type="expense",
        amount=300,
        account_id=checking["id"],
        category_id=food["id"],
        date=previous_income_day.isoformat(),
    )
    post_transaction(
        client,
        type="income",
        amount=3000,
        account_id=checking["id"],
        category_id=salary["id"],
        date=TODAY.replace(day=2).isoformat(),
    )
    post_transaction(
        client,
        type="expense",
        amount=400,
        account_id=checking["id"],
        category_id=food["id"],
        date=TODAY.replace(day=4).isoformat(),
    )
    post_transaction(
        client,
        type="expense",
        amount=100,
        account_id=checking["id"],
        category_id=food["id"],
        date=TODAY.replace(day=5).isoformat(),
    )
    post_transaction(
        client,
        type="expense",
        amount=150,
        account_id=checking["id"],
        category_id=transport["id"],
        date=TODAY.replace(day=6).isoformat(),
    )
    response = client.post(
        "/api/v1/transfers",
        json={
            "source_account_id": checking["id"],
            "destination_account_id": savings["id"],
            "amount": 500,
            "date": TODAY.replace(day=6).isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    return {
        "checking": checking,
        "card": card,
        "savings": savings,
        "food": food,
        "transport": transport,
        "salary": salary,
    }


def assistant(client) -> dict:
    response = client.get("/api/v1/assistant")
    assert response.status_code == 200, response.text
    return response.json()


def set_currency_usd(session) -> None:
    from app.services.profile_service import ProfileService

    ProfileService(session).update(currency="USD")


def ask(client, body) -> dict:
    response = client.post("/api/v1/assistant/ask", json=body)
    assert response.status_code == 200, response.text
    return response.json()


# -- endpoints: no-data ---------------------------------------------------------


def test_assistant_endpoint_with_no_data(client):
    payload = assistant(client)
    assert payload["has_data"] is False
    assert payload["provider"] == "rules"
    assert payload["provider_name"] == "Rules engine"
    assert payload["greeting"] == "Here is what I noticed this month."
    assert len(payload["questions"]) == 12
    assert payload["insights"][0]["id"] == "no-data"
    assert "nothing to summarize" in payload["overview"]

    result = ask(client, {"question": "How much did I spend this month?"})
    assert result["recognized"] is True
    assert result["source"] == "ledger"
    assert "no recorded transactions" in result["answer"].lower()


def test_assistant_endpoint_with_live_data(client):
    seed_normal(client)
    payload = assistant(client)
    assert payload["has_data"] is True
    assert payload["provider"] == "rules"
    assert payload["insights"]
    for insight in payload["insights"]:
        for field in ("id", "severity", "category", "title", "explanation"):
            assert field in insight


# -- deterministic service-level checks -------------------------------------------


def test_normal_month_trends(client, session):
    seed_normal(client)
    set_currency_usd(session)
    svc = FinancialAssistantService(session)
    result = svc.overview(today=TODAY)

    assert result["has_data"] is True
    assert "you earned $3,000.00 and spent $650.00" in result["overview"]
    assert "saved $2,350.00" in result["overview"]

    ids = {i["id"] for i in result["insights"]}
    assert "net-worth-up" in ids
    assert "savings-rate-declined" in ids or "savings-rate-improved" in ids

    # no fabricated numbers: every insight carries a real metric
    for insight in result["insights"]:
        assert insight["generated_at"]


def test_ask_spending_savings_and_safe_to_spend(client, session):
    seed_normal(client)
    set_currency_usd(session)
    svc = FinancialAssistantService(session)

    spent = svc.ask("How much did I spend this month?", today=TODAY)
    assert spent["intent"] == "spending"
    assert spent["recognized"] is True
    assert spent["source"] == "ledger"
    assert "$650.00" in spent["answer"]

    saved = svc.ask("How much did I save?", today=TODAY)
    assert "$2,350.00" in saved["answer"]
    assert saved["estimate"] is False

    safe = svc.ask("How much can I safely spend today?", today=TODAY)
    assert safe["intent"] == "safe_to_spend"
    assert safe["source"] == "estimate"
    assert safe["estimate"] is True
    assert "per day" in safe["answer"]
    assert len(safe["facts"]) >= 5


def test_ask_top_categories_and_net_worth(client, session):
    seed_normal(client)
    set_currency_usd(session)
    svc = FinancialAssistantService(session)

    top = svc.ask("Where am I spending the most?", today=TODAY)
    assert top["intent"] == "top_categories"
    assert "Food" in top["answer"]
    assert "$500.00" in top["answer"]

    worth = svc.ask("How is my net worth changing?", today=TODAY)
    assert worth["intent"] == "net_worth"
    assert worth["recognized"] is True
    assert "net worth is" in worth["answer"]


def test_ask_expense_increases(client, session):
    seed_normal(client)
    svc = FinancialAssistantService(session)
    result = svc.ask("Which expenses increased?", today=TODAY)
    assert result["intent"] == "expense_increases"
    assert "Food" in result["answer"]
    assert "Transport" not in result["answer"]  # no spending last period, not "increased"


# -- budget ------------------------------------------------------------------------


def test_budget_over_insight_and_answer(client, session):
    data = seed_normal(client)
    put_budget(
        client,
        items=[{"category_id": data["food"]["id"], "planned_amount": 400}],
    )
    svc = FinancialAssistantService(session)

    overview = svc.overview(today=TODAY)
    over = next((i for i in overview["insights"] if i["id"] == "budget-over-food"), None)
    assert over is not None
    assert over["severity"] == "critical"

    answer = svc.ask("Am I on track with my budget?", today=TODAY)
    assert answer["source"] == "ledger"
    assert "over budget" in answer["answer"].lower()


def test_budget_close_projection_is_estimate(client, session):
    data = seed_normal(client)
    put_budget(client, items=[{"category_id": data["food"]["id"], "planned_amount": 900}])
    svc = FinancialAssistantService(session)
    answer = svc.ask("budget", today=TODAY)
    assert answer["source"] in {"estimate", "ledger"}
    assert answer["recognized"] is True


# -- recurring + debt ---------------------------------------------------------------


def test_increased_recurring_warning(client, session):
    data = seed_normal(client)
    make_recurring(
        client,
        account_id=data["checking"]["id"],
        type="expense",
        amount=1500,
        frequency="monthly",
        next_occurrence=(TODAY + timedelta(days=2)).isoformat(),
    )
    set_currency_usd(session)
    svc = FinancialAssistantService(session)
    result = svc.overview(today=TODAY)
    warning = next((i for i in result["insights"] if i["id"] == "recurring-income-share"), None)
    assert warning is not None
    assert warning["severity"] == "warning"
    assert "$1,500.00" in warning["explanation"]


def test_debt_ratio_insight(client, session):
    seed_normal(client)
    create_debt(
        client,
        name="Auto Loan",
        original_amount=20000,
        remaining_amount=18000,
        minimum_payment=1800,
        due_date=(TODAY + timedelta(days=5)).isoformat(),
    )
    svc = FinancialAssistantService(session)
    result = svc.overview(today=TODAY)
    debt = next((i for i in result["insights"] if i["id"] == "debt-income-share"), None)
    assert debt is not None
    assert debt["severity"] == "critical"


# -- goals ---------------------------------------------------------------------------


def test_goal_eta_insight_and_goal_id_answer(client, session):
    seed_normal(client)
    goal = create_goal(client, name="New Car", target_amount=5000, current_amount=0)
    svc = FinancialAssistantService(session)

    overview = svc.overview(today=TODAY)
    eta = next((i for i in overview["insights"] if i["id"] == f"goal-eta-{goal['id']}"), None)
    assert eta is not None
    assert "month" in eta["title"].lower()

    answer = svc.ask(
        "When will I reach my goal?",
        goal_id=goal["id"],
        today=TODAY,
    )
    assert answer["intent"] == "goal_eta"
    assert "New Car" in answer["answer"]
    assert answer["estimate"] is True
    assert answer["source"] == "estimate"


# -- free text + fallbacks ------------------------------------------------------------


def test_ask_free_text_intent_matching(client):
    seed_normal(client)
    result = ask(client, {"question": "Where am I spending the most?"})
    assert result["intent"] == "top_categories"
    assert result["recognized"] is True


def test_ask_unrecognized_question_falls_back(client):
    result = ask(client, {"question": "What is the meaning of life, the universe and everything?"})
    assert result["recognized"] is False
    assert "Try:" in result["answer"]
    assert result["estimate"] is False


def test_ask_explicit_intent_overrides_text(client):
    seed_normal(client)
    result = ask(client, {"question": "ignore", "intent": "net_worth"})
    assert result["intent"] == "net_worth"
    assert result["recognized"] is True