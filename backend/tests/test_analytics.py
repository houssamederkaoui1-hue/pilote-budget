"""Analytics engine + Safe-to-Spend: trends, history, forecasts, health.

Service methods take an explicit ``today`` so these tests are deterministic;
the endpoints use the real clock and are covered by the shape tests.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.services.analytics_service import AnalyticsService
from app.services.profile_service import ProfileService

# Fixed reference date for deterministic service-level assertions.
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


def seed(client, today: date) -> dict:
    """Two periods of real activity plus noise a transfer/void never counts."""
    checking = create_account(client, "Checking", opening_balance=1000)
    card = create_account(client, "Credit Card", opening_balance=-200, type="credit_card")
    savings_account = create_account(client, "Savings", opening_balance=0)

    food = create_category(client, "Food", "expense")
    transport = create_category(client, "Transport", "expense")
    salary = create_category(client, "Salary", "income")

    prev_day = (today.replace(day=1) - timedelta(days=1)).replace(day=2)

    post_transaction(
        client,
        type="income",
        amount=2500,
        account_id=checking["id"],
        category_id=salary["id"],
        date=prev_day.isoformat(),
        description="Salary",
    )
    post_transaction(
        client,
        type="expense",
        amount=300,
        account_id=checking["id"],
        category_id=food["id"],
        date=prev_day.isoformat(),
    )

    post_transaction(
        client,
        type="income",
        amount=3000,
        account_id=checking["id"],
        category_id=salary["id"],
        date=today.replace(day=2).isoformat(),
    )
    post_transaction(
        client,
        type="expense",
        amount=400,
        account_id=checking["id"],
        category_id=food["id"],
        date=today.replace(day=4).isoformat(),
    )
    post_transaction(
        client,
        type="expense",
        amount=100,
        account_id=checking["id"],
        category_id=food["id"],
        date=today.replace(day=5).isoformat(),
    )
    post_transaction(
        client,
        type="expense",
        amount=150,
        account_id=checking["id"],
        category_id=transport["id"],
        date=today.replace(day=6).isoformat(),
    )
    # Noise: void rows never count as expense.
    post_transaction(
        client,
        type="expense",
        amount=999,
        account_id=checking["id"],
        category_id=food["id"],
        date=today.replace(day=6).isoformat(),
        status="void",
    )
    # Noise: transfers are not income/expense.
    response = client.post(
        "/api/v1/transfers",
        json={
            "source_account_id": checking["id"],
            "destination_account_id": savings_account["id"],
            "amount": 500,
            "date": today.replace(day=6).isoformat(),
        },
    )
    assert response.status_code == 201, response.text

    return {
        "checking": checking,
        "card": card,
        "savings": savings_account,
        "food": food,
        "transport": transport,
        "salary": salary,
    }


def summary(session, today: date = TODAY) -> dict:
    return AnalyticsService(session).summary(today)


def safe_to_spend(session, today: date = TODAY) -> dict:
    return AnalyticsService(session).safe_to_spend(today)


# -- endpoint smoke -----------------------------------------------------------


def test_endpoints_return_200(client):
    seed(client, date.today())
    response = client.get("/api/v1/analytics")
    assert response.status_code == 200, response.text
    payload = response.json()
    for key in (
        "as_of",
        "period",
        "previous_period",
        "income",
        "expenses",
        "savings",
        "categories",
        "net_worth",
        "net_worth_history",
        "budget",
        "history",
        "forecasts",
        "health",
        "insights",
    ):
        assert key in payload, f"missing {key}"
    assert payload["has_data"] is True

    response = client.get("/api/v1/analytics/safe-to-spend")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ok"


def test_endpoints_work_with_no_data(client):
    response = client.get("/api/v1/analytics")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["has_data"] is False
    assert payload["transactions_count"] == 0
    assert payload["categories"] == []
    assert payload["income"]["current"] == 0
    assert payload["insights"][0]["key"] == "no-data"

    response = client.get("/api/v1/analytics/safe-to-spend")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "insufficient"
    assert payload["safe_to_spend_daily"] is None
    assert payload["available_money"] is None
    assert "transaction history" in payload["explanation"]


# -- income / expenses / savings trends --------------------------------------


def test_trends_income_expense_savings(client, session):
    seed(client, TODAY)
    result = summary(session)

    assert result["has_data"] is True
    assert result["transactions_count"] == 6  # void row excluded

    assert result["income"]["current"] == 3000
    assert result["income"]["previous"] == 2500
    assert result["income"]["change_pct"] == 20.0
    assert result["income"]["trend"] == "up"

    assert result["expenses"]["current"] == 650
    assert result["expenses"]["previous"] == 300
    assert result["expenses"]["change_pct"] == 116.7
    assert result["expenses"]["trend"] == "up"

    assert result["savings"]["current"] == 2350
    assert result["savings"]["previous"] == 2200
    assert result["savings"]["change_pct"] == 6.8
    assert result["savings"]["rate"] == round(2350 / 3000 * 100, 1)
    assert result["savings"]["rate_status"] == "positive"
    # Only one completed period carries income, so the historical rate is that
    # period's rate (never a guess).
    assert result["savings"]["historical_rate"] == 88.0


def test_history_and_net_worth_series(client, session):
    seed(client, TODAY)
    result = summary(session)

    assert len(result["history"]) == 7
    assert len(result["net_worth_history"]) == 7

    current = result["history"][-1]
    assert current["closed"] is False
    assert current["income"] == 3000
    assert current["expense"] == 650
    assert current["net"] == 2350
    assert current["savings_rate"] == round(2350 / 3000 * 100, 1)

    previous = result["history"][-2]
    assert previous["closed"] is True
    assert previous["income"] == 2500
    assert previous["expense"] == 300
    assert previous["net"] == 2200

    # Real ledger facts only: no fabricated periods before the data.
    assert result["history"][0]["income"] == 0
    assert result["history"][0]["expense"] == 0
    assert result["history"][0]["savings_rate"] is None

    # Opening balances only, as-of the earliest window's end.
    assert result["net_worth_history"][0]["net_worth"] == 800
    # Everything posted to date (incl. September) + opening balances:
    # 800 opening + 5500 income - 950 expense = 5350.
    assert result["net_worth_history"][-1]["net_worth"] == 5350


def test_category_breakdown_and_shares(client, session):
    seed(client, TODAY)
    result = summary(session)

    categories = result["categories"]
    assert [item["category_name"] for item in categories] == ["Food", "Transport"]
    assert categories[0]["amount"] == 500
    assert categories[0]["share_pct"] == round(500 / 650 * 100, 1)
    assert categories[0]["change_pct"] == 66.7
    assert categories[1]["amount"] == 150
    assert categories[1]["share_pct"] == round(150 / 650 * 100, 1)
    assert categories[1]["change_pct"] is None  # new category, no baseline
    # Transfers and void rows are invisible to the breakdown.
    assert sum(item["amount"] for item in categories) == 650


def test_budget_and_net_worth_metrics(client, session):
    seed(client, TODAY)
    result = summary(session)

    budget = result["budget"]
    assert budget["allocation"]["has_allocation"] is False
    assert budget["totals"]["actual"] == 650
    assert budget["totals"]["pct_used"] is None  # unbudgeted spending
    assert budget["totals"]["over_budget"] is True
    assert len(budget["items"]) == 2

    net_worth = result["net_worth"]
    # balances: checking 1000+2500-300+3000-650-500 = 5050,
    # savings 0+500 = 500 (asset) and card -200 (liability).
    assert net_worth["assets"] == 5550
    assert net_worth["liabilities"] == 200
    assert net_worth["net_worth"] == 5350
    assert net_worth["previous"] == 3000
    assert net_worth["change_pct"] == 78.3


def test_forecasts_are_pace_estimates(client, session):
    seed(client, TODAY)
    result = summary(session)
    forecasts = result["forecasts"]

    # 8 days elapsed of a 31-day period (2026-10-01 .. 2026-10-31).
    assert forecasts["spending"]["actual"] == 650
    assert forecasts["spending"]["estimated"] == round(650 / 8 * 31, 2)
    assert forecasts["spending"]["is_estimate"] is True

    assert forecasts["income"]["estimated"] == round(3000 / 8 * 31, 2)
    estimated_savings = round(
        round(3000 / 8 * 31, 2) - round(650 / 8 * 31, 2), 2
    )
    assert forecasts["savings"]["estimated"] == estimated_savings
    assert forecasts["available"]["opening"] == 3000
    assert forecasts["available"]["current"] == 5350
    assert forecasts["available"]["estimated_end"] == round(3000 + estimated_savings, 2)
    assert forecasts["note"]  # always explains the estimate


def test_forecast_on_period_first_day_uses_one_day_of_pace(client, session):
    account = create_account(client, "Checking", opening_balance=500)
    post_transaction(
        client,
        type="income",
        amount=100,
        account_id=account["id"],
        date=date(2026, 10, 1).isoformat(),
    )
    result = summary(session, today=date(2026, 10, 1))
    forecasts = result["forecasts"]
    # Day 1 of 31: one observation of 100 income -> straight-line 100/1 * 31.
    assert forecasts["income"]["actual"] == 100
    assert forecasts["income"]["estimated"] == 3100.0
    assert forecasts["income"]["is_estimate"] is True
    assert forecasts["spending"]["actual"] == 0
    assert forecasts["spending"]["estimated"] == 0.0


# -- financial health + insights ---------------------------------------------


def test_financial_health_indicators(client, session):
    seed(client, TODAY)
    health = summary(session)["health"]

    assert health["savings_rate"] == round(2350 / 3000 * 100, 1)
    assert health["savings_rate_status"] == "positive"
    assert health["budget_pct_used"] is None
    assert health["budget_over"] is True
    assert health["recurring_expense_ratio"] == 0.0  # no fixed bills yet
    assert health["recurring_expense_ratio_status"] == "low"
    assert health["debt_burden"] == 0.0
    assert health["debt_burden_status"] == "low"
    assert health["cashflow_net"] == 2350
    assert health["cashflow_status"] == "positive"
    # Only completed months count: the in-progress October is excluded.
    assert health["cashflow_streak"] == 1
    assert health["upcoming_obligations_count"] == 0


def test_insights_are_deterministic_and_limited(client, session):
    seed(client, TODAY)
    insights = summary(session)["insights"]

    keys = [insight["key"] for insight in insights]
    assert keys[0] == "top-category"
    assert "expense-trend" in keys
    assert "savings-rate" in keys
    assert "budget-over" in keys
    assert "net-worth-change" in keys
    # Only ONE closed month is positive, so no multi-month streak is claimed.
    assert "cashflow-streak" not in keys
    assert len(insights) <= 6
    assert all(insight["title"] and insight["description"] for insight in insights)


# -- Safe-to-Spend ------------------------------------------------------------


def test_safe_to_spend_base_formula(client, session):
    seed(client, TODAY)
    result = safe_to_spend(session)

    assert result["status"] == "ok"
    assert result["is_estimate"] is True
    # asset balances 5050+500 minus owed card 200
    assert result["available_money"] == 5350
    assert result["obligations"] == []
    assert result["obligations_total"] == 0
    assert result["planned_savings"] == 0
    assert result["reserve_amount"] == 0
    assert result["committed_total"] == 0
    assert result["discretionary"] == 5350
    # 2026-10-08 .. 2026-10-31 inclusive
    assert result["remaining_days"] == 24
    assert result["safe_to_spend_daily"] == round(5350 / 24, 2)
    assert "222.92" in result["explanation"]
    assert "not financial advice" in result["disclaimer"]


def test_safe_to_spend_subtracts_obligations_planned_savings_and_reserve(client, session):
    seed(client, TODAY)

    response = client.put(
        "/api/v1/budgets",
        params={"period": TODAY.isoformat()},
        json={
            "allocation": {
                "income": 3000,
                "needs": 1500,
                "wants": 600,
                "savings": 600,
                "other": 300,
            },
            "items": [],
        },
    )
    assert response.status_code == 200, response.text

    response = client.post(
        "/api/v1/recurring",
        json={
            "account_id": create_account(client, "Rent Checking")["id"],
            "type": "expense",
            "amount": 400,
            "frequency": "monthly",
            "next_occurrence": "2026-10-20",
            "description": "Rent",
        },
    )
    assert response.status_code == 201, response.text
    response = client.post(
        "/api/v1/recurring",
        json={
            "account_id": create_account(client, "Side Checking")["id"],
            "type": "income",
            "amount": 1000,
            "frequency": "monthly",
            "next_occurrence": "2026-10-15",
            "description": "Side income",
        },
    )
    assert response.status_code == 201, response.text
    response = client.post(
        "/api/v1/recurring",
        json={
            "account_id": create_account(client, "Later Checking")["id"],
            "type": "expense",
            "amount": 999,
            "frequency": "monthly",
            "next_occurrence": "2026-12-01",
            "description": "Outside period",
        },
    )
    assert response.status_code == 201, response.text
    response = client.post(
        "/api/v1/debts",
        json={
            "name": "Card payment",
            "original_amount": 1000,
            "remaining_amount": 1000,
            "minimum_payment": 200,
            "due_date": "2026-10-25",
        },
    )
    assert response.status_code == 201, response.text

    result = safe_to_spend(session)
    kinds = [item["kind"] for item in result["obligations"]]
    assert kinds == ["recurring", "debt"]
    assert [item["amount"] for item in result["obligations"]] == [400, 200]
    assert result["obligations_total"] == 600
    assert result["planned_savings"] == 600
    assert result["committed_total"] == 1200
    assert result["discretionary"] == 4150
    assert result["safe_to_spend_daily"] == round(4150 / 24, 2)
    # Income obligations never count as money owed.
    assert all(item["kind"] != "income" for item in result["obligations"])


def test_safe_to_spend_requires_transaction_history(client):
    account = create_account(client, "Checking", opening_balance=5000)
    result = client.get("/api/v1/analytics/safe-to-spend").json()
    assert result["status"] == "insufficient"
    assert result["reason"]
    assert result["safe_to_spend_daily"] is None
    assert account["opening_balance"] == 5000


def test_safe_to_spend_excludes_archived_accounts(client, session):
    active = create_account(client, "Active", opening_balance=1000)
    archived = create_account(client, "Archived", opening_balance=900)
    client.patch(f"/api/v1/accounts/{archived['id']}", json={"active": False})
    post_transaction(
        client,
        type="income",
        amount=100,
        account_id=active["id"],
        date=TODAY.isoformat(),
    )

    result = safe_to_spend(session)
    assert result["status"] == "ok"
    assert result["available_money"] == 1100  # 900 frozen account excluded

    # ...but the archived money still counts toward net worth.
    net_worth = summary(session)["net_worth"]
    assert net_worth["assets"] == 2000


# -- liabilities, month boundaries, empty states -------------------------------


def test_debt_and_liability_handling(client, session):
    card = create_account(client, "Card", opening_balance=-300, type="credit_card")
    create_account(client, "Checking", opening_balance=1500)
    response = client.post(
        "/api/v1/debts",
        json={
            "name": "Card balance",
            "original_amount": 250,
            "remaining_amount": 250,
            "account_id": card["id"],
        },
    )
    assert response.status_code == 201, response.text

    result = summary(session)
    assert result["net_worth"]["assets"] == 1500
    assert result["net_worth"]["liabilities"] == 300
    assert result["net_worth"]["net_worth"] == 1200
    # Debt linked to the liability account is covered by its balance: no
    # double counting in the debt-adjusted figure either.
    assert result["net_worth"]["net_worth_including_debts"] == 1200
    assert result["health"]["debt_burden"] == round(250 / 1500 * 100, 1)
    assert result["health"]["debt_burden_status"] == "low"


def test_month_boundary_with_month_start_day_15(client, session):
    ProfileService(session).update(month_start_day=15)
    session.commit()

    account = create_account(client, "Checking", opening_balance=1000)
    food = create_category(client, "Food", "expense")
    post_transaction(
        client,
        type="expense",
        amount=90,
        account_id=account["id"],
        category_id=food["id"],
        date=date(2026, 10, 20).isoformat(),
    )
    post_transaction(
        client,
        type="expense",
        amount=10,
        account_id=account["id"],
        category_id=food["id"],
        date=date(2026, 10, 10).isoformat(),
    )

    result = summary(session, today=date(2026, 10, 20))
    assert result["period"]["period_start"] == date(2026, 10, 15)
    assert result["period"]["period_end"] == date(2026, 11, 14)
    # day-15 periods run 15th..14th, so the previous one is Sep 15..Oct 14.
    assert result["previous_period"]["period_start"] == date(2026, 9, 15)
    assert result["previous_period"]["period_end"] == date(2026, 10, 14)
    assert result["expenses"]["current"] == 90
    assert result["expenses"]["previous"] == 10
    assert result["expenses"]["change_pct"] == 800.0
    assert result["categories"][0]["amount"] == 90
    assert result["categories"][0]["share_pct"] == 100.0


def test_one_month_of_data_state(client, session):
    account = create_account(client, "Checking", opening_balance=0)
    post_transaction(
        client,
        type="income",
        amount=2000,
        account_id=account["id"],
        date=date(2026, 10, 2).isoformat(),
    )
    post_transaction(
        client,
        type="expense",
        amount=500,
        account_id=account["id"],
        date=date(2026, 10, 3).isoformat(),
    )

    result = summary(session, today=date(2026, 10, 8))
    assert result["has_data"] is True
    assert result["expenses"]["previous"] == 0
    # No meaningful baseline: going 0 -> 500 is not reported as "+100%".
    assert result["expenses"]["change_pct"] is None
    assert result["savings"]["historical_rate"] is None
    # Empty months carry zeros but no invented savings rate.
    assert result["history"][0]["income"] == 0
    assert result["history"][0]["savings_rate"] is None
    assert result["net_worth_history"][0]["net_worth"] == 0


def test_streak_counts_completed_months_only(client, session):
    account = create_account(client, "Checking", opening_balance=0)
    salary = create_category(client, "Salary", "income")
    food = create_category(client, "Food", "expense")

    def month(year, month_no, income, expense):
        post_transaction(
            client, type="income", amount=income,
            account_id=account["id"], category_id=salary["id"],
            date=date(year, month_no, 5).isoformat(),
        )
        post_transaction(
            client, type="expense", amount=expense,
            account_id=account["id"], category_id=food["id"],
            date=date(year, month_no, 6).isoformat(),
        )

    # Jul, Aug, Sep closed periods are all cashflow-positive.
    for mon, inc, exp in (
        (7, 1000, 100), (8, 1000, 200), (9, 1000, 300),
    ):
        month(2026, mon, inc, exp)
    # Current (open) October is also positive — it must NOT extend the streak.
    month(2026, 10, 1000, 400)

    result = summary(session, today=date(2026, 10, 8))
    assert result["health"]["cashflow_streak"] == 3
    keys = [insight["key"] for insight in result["insights"]]
    assert "cashflow-streak" in keys
    streak_insight = next(i for i in result["insights"] if i["key"] == "cashflow-streak")
    assert "3" in streak_insight["title"]


def test_overdue_obligations_stay_committed(client, session):
    seed(client, TODAY)
    client.put(
        "/api/v1/budgets",
        params={"period": TODAY.isoformat()},
        json={
            "allocation": {"income": 3000, "needs": 1500, "wants": 600,
                           "savings": 600, "other": 300},
            "items": [],
        },
    )
    client.post(
        "/api/v1/debts",
        json={
            "name": "Overdue card",
            "original_amount": 500,
            "remaining_amount": 500,
            "minimum_payment": 200,
            "due_date": "2026-10-03",  # already past TODAY (Oct 8)
        },
    )

    result = safe_to_spend(session, today=TODAY)
    assert result["status"] == "ok"
    assert len(result["obligations"]) == 1
    assert result["obligations"][0]["kind"] == "debt"
    assert result["obligations"][0]["overdue"] is True
    assert result["obligations_total"] == 200
    # 5350 available - 200 overdue = 5150 discretionary (planned savings 600,
    # reserve 0) -> 5150 - 600 = 4550.
    assert result["discretionary"] == 4550


def test_archived_liability_is_still_deducted(client, session):
    active = create_account(client, "Checking", opening_balance=2000)
    archived_card = create_account(
        client, "Old Card", opening_balance=-300, type="credit_card"
    )
    client.patch(f"/api/v1/accounts/{archived_card['id']}", json={"active": False})
    post_transaction(
        client,
        type="income",
        amount=100,
        account_id=active["id"],
        date=TODAY.isoformat(),
    )

    # Archived money is frozen (2100 assets), but the archived card balance is
    # still owed, so 300 is deducted from what you can spend.
    result = safe_to_spend(session, today=TODAY)
    assert result["status"] == "ok"
    assert result["available_money"] == 1800