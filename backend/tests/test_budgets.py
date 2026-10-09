"""Budget engine: allocation + category budgets, planned/actual/remaining/pct.

The engine (``BudgetService``) is the only place these numbers are computed.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

ALLOCATION = {
    "income": 3000,
    "needs": 1500,
    "wants": 600,
    "savings": 600,
    "other": 300,
}


def today() -> date:
    return date.today()


def period_bounds() -> tuple[date, date]:
    start = today().replace(day=1)
    return start, start.replace(day=monthrange(start.year, start.month)[1])


def create_account(client, name, **payload):
    return client.post("/api/v1/accounts", json={"name": name, **payload}).json()


def add_expense(client, account_id, category_id, amount, day, **payload):
    response = client.post(
        "/api/v1/transactions",
        json={
            "type": "expense",
            "amount": amount,
            "account_id": account_id,
            "category_id": category_id,
            "date": day.isoformat(),
            **payload,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def add_income(client, account_id, amount, day, **payload):
    response = client.post(
        "/api/v1/transactions",
        json={
            "type": "income",
            "amount": amount,
            "account_id": account_id,
            "date": day.isoformat(),
            **payload,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def make_expense_category(client, name):
    response = client.post(
        "/api/v1/categories", json={"name": name, "type": "expense"}
    )
    assert response.status_code == 201, response.text
    return response.json()


def make_income_category(client, name):
    response = client.post(
        "/api/v1/categories", json={"name": name, "type": "income"}
    )
    assert response.status_code == 201, response.text
    return response.json()


def put_budget(client, allocation=None, items=None, period=None):
    response = client.put(
        "/api/v1/budgets",
        params={"period": (period or today()).isoformat()},
        json={
            "allocation": allocation,
            "items": items or [],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def get_budget(client, period=None):
    response = client.get(
        "/api/v1/budgets",
        params={"period": (period or today()).isoformat()},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_empty_month_returns_zeroed_summary(client):
    result = get_budget(client)
    assert result["allocation"]["has_allocation"] is False
    assert result["allocation"]["planned_total"] == 0
    assert result["totals"] == {
        "planned": 0,
        "actual": 0,
        "remaining": 0,
        "pct_used": 0.0,
        "over_budget": False,
    }
    assert result["items"] == []
    assert result["approaching"] == []
    assert result["exceeding"] == []


def test_put_sets_allocation(client):
    result = put_budget(client, allocation=ALLOCATION)
    assert result["allocation"]["income_amount"] == 3000
    assert result["allocation"]["planned_total"] == 3000
    assert result["allocation"]["has_allocation"] is True
    assert result["allocation"]["remaining_total"] == 3000
    assert result["allocation"]["pct_used"] == 0.0


def test_put_allocation_and_items(client):
    food = make_expense_category(client, "Food")
    transport = make_expense_category(client, "Transport")
    result = put_budget(
        client,
        allocation=ALLOCATION,
        items=[
            {"category_id": food["id"], "planned_amount": 400},
            {"category_id": transport["id"], "planned_amount": 200},
        ],
    )
    names = {item["category_name"]: item for item in result["items"]}
    assert names["Food"]["planned_amount"] == 400
    assert names["Transport"]["planned_amount"] == 200
    assert result["totals"]["planned"] == 600


def test_actual_remaining_and_pct(client):
    account = create_account(client, "Checking")
    food = make_expense_category(client, "Food")
    transport = make_expense_category(client, "Transport")
    start, end = period_bounds()
    add_expense(client, account["id"], food["id"], 300, start + timedelta(days=2))
    add_expense(client, account["id"], transport["id"], 50, start + timedelta(days=3))

    result = put_budget(
        client,
        allocation=ALLOCATION,
        items=[
            {"category_id": food["id"], "planned_amount": 400},
            {"category_id": transport["id"], "planned_amount": 200},
        ],
    )

    items = {item["category_name"]: item for item in result["items"]}
    food_row = items["Food"]
    assert food_row["actual_amount"] == 300
    assert food_row["remaining_amount"] == 100
    assert food_row["pct_used"] == 75.0
    assert food_row["over_budget"] is False
    assert food_row["status"] == "healthy"

    assert result["allocation"]["actual_total"] == 350
    assert result["allocation"]["remaining_total"] == 2650  # 3000 - 350
    assert result["allocation"]["pct_used"] == round(350 / 3000 * 100, 1)

    assert result["totals"]["actual"] == 350
    assert result["totals"]["remaining"] == 250
    assert result["totals"]["pct_used"] == round(350 / 600 * 100, 1)


def test_over_budget_and_exceeding(client):
    account = create_account(client, "Checking")
    food = make_expense_category(client, "Food")
    start, end = period_bounds()
    add_expense(client, account["id"], food["id"], 500, start + timedelta(days=1))
    add_expense(client, account["id"], food["id"], 50, start + timedelta(days=2))

    result = put_budget(
        client,
        items=[{"category_id": food["id"], "planned_amount": 400}],
    )
    food_row = result["items"][0]
    assert food_row["pct_used"] == 137.5
    assert food_row["over_budget"] is True
    assert food_row["status"] == "over"
    assert food_row["remaining_amount"] == -150
    assert food["id"] in result["exceeding"]
    assert result["totals"]["over_budget"] is True


def test_totals_include_uncategorized_and_archived_spending(client):
    account = create_account(client, "Checking")
    food = make_expense_category(client, "Food")
    transport = make_expense_category(client, "Transport")
    legacy = make_expense_category(client, "Legacy")
    start, end = period_bounds()

    # Planned + categorized spending.
    add_expense(client, account["id"], food["id"], 100, start + timedelta(days=2))
    # Uncategorized spending (no category).
    add_expense(client, account["id"], None, 50, start + timedelta(days=3))
    # Spending on a category that is later archived still happened.
    add_expense(client, account["id"], legacy["id"], 30, start + timedelta(days=4))
    client.patch(f"/api/v1/categories/{legacy['id']}", json={"active": False})

    result = put_budget(
        client,
        allocation=ALLOCATION,
        items=[
            {"category_id": food["id"], "planned_amount": 400},
            {"category_id": transport["id"], "planned_amount": 200},
        ],
    )
    # 100 (planned category) + 50 (uncategorized) + 30 (archived category).
    assert result["allocation"]["actual_total"] == 180
    assert result["allocation"]["remaining_total"] == 2820
    assert result["totals"]["actual"] == 180
    assert result["totals"]["planned"] == 600
    assert result["totals"]["over_budget"] is False
    assert result["totals"]["pct_used"] == round(180 / 600 * 100, 1)
    # Items reflect active planned categories only: the uncategorized and
    # archived spending are invisible row-by-row but not lost from totals.
    assert result["items"][0]["category_name"] == "Food"
    assert result["items"][0]["actual_amount"] == 100


def test_approaching_threshold(client):
    account = create_account(client, "Checking")
    food = make_expense_category(client, "Food")
    start, end = period_bounds()
    add_expense(client, account["id"], food["id"], 85, start + timedelta(days=1))

    result = put_budget(
        client,
        items=[{"category_id": food["id"], "planned_amount": 100}],
    )
    food_row = result["items"][0]
    assert food_row["pct_used"] == 85.0
    assert food_row["over_budget"] is False
    assert food_row["status"] == "approaching"
    assert food["id"] in result["approaching"]


def test_spending_on_unbudgeted_category_is_over(client):
    account = create_account(client, "Checking")
    food = make_expense_category(client, "Food")
    start, end = period_bounds()
    add_expense(client, account["id"], food["id"], 25, start + timedelta(days=1))

    result = get_budget(client)
    assert len(result["items"]) == 1
    row = result["items"][0]
    assert row["planned_amount"] == 0
    assert row["actual_amount"] == 25
    assert row["pct_used"] is None
    assert row["over_budget"] is True
    assert row["status"] == "over"
    assert food["id"] in result["exceeding"]


def test_void_and_transfer_and_income_do_not_count(client):
    account = create_account(client, "Checking")
    savings = create_account(client, "Savings")
    food = make_expense_category(client, "Food")
    start, end = period_bounds()

    response = client.post(
        "/api/v1/transactions",
        json={
            "type": "expense",
            "amount": 999,
            "account_id": account["id"],
            "category_id": food["id"],
            "date": (start + timedelta(days=1)).isoformat(),
            "status": "void",
        },
    )
    assert response.status_code == 201
    # transfer (excluded from budgets entirely)
    response = client.post(
        "/api/v1/transfers",
        json={
            "source_account_id": account["id"],
            "destination_account_id": savings["id"],
            "amount": 800,
            "date": (start + timedelta(days=1)).isoformat(),
        },
    )
    assert response.status_code == 201
    # income never counts as expense
    add_income(client, account["id"], 5000, start + timedelta(days=1))

    result = get_budget(client)
    assert result["allocation"]["actual_total"] == 0
    assert result["totals"]["actual"] == 0
    assert result["items"] == []


def test_put_replaces_previous_plan(client):
    food = make_expense_category(client, "Food")
    transport = make_expense_category(client, "Transport")

    put_budget(client, allocation=ALLOCATION, items=[{"category_id": food["id"], "planned_amount": 400}])
    result = put_budget(
        client,
        allocation={"income": 2500, "needs": 1200},
        items=[{"category_id": transport["id"], "planned_amount": 150}],
    )
    assert result["allocation"]["income_amount"] == 2500
    assert result["allocation"]["needs_amount"] == 1200
    assert result["allocation"]["planned_total"] == 1200
    assert [item["category_id"] for item in result["items"]] == [transport["id"]]


def test_category_budget_requires_expense_type(client):
    salary = make_income_category(client, "Salary")
    response = client.put(
        "/api/v1/budgets",
        params={"period": today().isoformat()},
        json={"allocation": None, "items": [{"category_id": salary["id"], "planned_amount": 100}]},
    )
    assert response.status_code == 400
    assert "income" in response.json()["detail"]


def test_duplicate_category_item_rejected(client):
    food = make_expense_category(client, "Food")
    response = client.put(
        "/api/v1/budgets",
        params={"period": today().isoformat()},
        json={
            "allocation": None,
            "items": [
                {"category_id": food["id"], "planned_amount": 100},
                {"category_id": food["id"], "planned_amount": 200},
            ],
        },
    )
    assert response.status_code == 400
    assert "more than once" in response.json()["detail"]


def test_negative_planned_rejected(client):
    food = make_expense_category(client, "Food")
    response = client.put(
        "/api/v1/budgets",
        params={"period": today().isoformat()},
        json={"allocation": None, "items": [{"category_id": food["id"], "planned_amount": -5}]},
    )
    assert response.status_code == 422


def test_archived_category_rejected(client):
    food = make_expense_category(client, "Food")
    client.patch(f"/api/v1/categories/{food['id']}", json={"active": False})
    response = client.put(
        "/api/v1/budgets",
        params={"period": today().isoformat()},
        json={"allocation": None, "items": [{"category_id": food["id"], "planned_amount": 100}]},
    )
    assert response.status_code == 400


def test_period_alignment_with_month_start_day(session, client):
    from app.services.profile_service import ProfileService
    from app.services.budget_service import BudgetService

    ProfileService(session).update(month_start_day=15)
    session.commit()

    account = create_account(client, "Checking")
    food = make_expense_category(client, "Food")
    add_expense(client, account["id"], food["id"], 90, date(2026, 10, 20))
    add_expense(client, account["id"], food["id"], 10, date(2026, 10, 10))  # previous period

    result = put_budget(client, items=[{"category_id": food["id"], "planned_amount": 100}], period=date(2026, 10, 20))
    assert result["period_start"] == "2026-10-15"
    assert result["period_end"] == "2026-11-14"
    assert result["items"][0]["actual_amount"] == 90