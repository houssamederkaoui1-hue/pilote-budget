"""Final product-acceptance scenarios A–I (financial correctness).

Each scenario tells one end-to-end story with exact expected money figures.
Service-level reads take an explicit ``today`` so the numbers are stable on
any run date; endpoint-level checks anchor on the real clock (the same way
the UI reads them). ``read()`` rolls the shared session so commits made
through the API client are visible to the service-level assertions.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.domain.schedules import months_shift
from app.services.analytics_service import AnalyticsService
from app.services.profile_service import ProfileService

# Fixed reference date for the deterministic service-level scenarios.
TODAY = date(2026, 10, 8)


# -- helpers -----------------------------------------------------------------


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


def post_transfer(client, source_account_id, destination_account_id, amount, day):
    response = client.post(
        "/api/v1/transfers",
        json={
            "source_account_id": source_account_id,
            "destination_account_id": destination_account_id,
            "amount": amount,
            "date": day.isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def put_budget(client, allocation=None, items=None, period=TODAY):
    response = client.put(
        "/api/v1/budgets",
        params={"period": period.isoformat()},
        json={"allocation": allocation, "items": items or []},
    )
    assert response.status_code == 200, response.text
    return response.json()


def summary(session, today=TODAY):
    return _service_read(session, lambda s: AnalyticsService(s).summary(today))


def safe_to_spend(session, today=TODAY):
    return _service_read(session, lambda s: AnalyticsService(s).safe_to_spend(today))


def _service_read(session, fn):
    """Run a service read against a fresh snapshot, then release the lock.

    SQLite (default journal mode) allows only one writer at a time; any open
    read transaction in this shared session would block client writes, so the
    snapshot is committed (ended) as soon as the read completes.
    """
    session.rollback()
    try:
        return fn(session)
    finally:
        session.commit()


def overview(client):
    response = client.get("/api/v1/overview")
    assert response.status_code == 200, response.text
    return response.json()


# -- A: multi-account net worth ----------------------------------------------


def test_scenario_a_multi_account_net_worth(client, session):
    create_account(client, "Checking", opening_balance=3000)
    create_account(client, "Savings", opening_balance=1000)
    create_account(client, "Card", opening_balance=-500, type="credit_card")

    result = overview(client)
    assert result["total_assets"] == 4000
    assert result["account_liabilities"] == 500
    assert result["debt_liabilities"] == 0
    assert result["total_liabilities"] == 500
    assert result["net_worth"] == 3500

    nw = summary(session)["net_worth"]
    assert nw["assets"] == 4000
    assert nw["liabilities"] == 500
    assert nw["net_worth"] == 3500
    # No debt records: the debt-adjusted figure matches the plain net worth.
    assert nw["net_worth_including_debts"] == 3500


# -- B: income, expenses, savings and category shares ------------------------


def test_scenario_b_income_expenses_savings_and_categories(client, session):
    checking = create_account(client, "Checking", opening_balance=0)
    salary = create_category(client, "Salary", "income")
    rent = create_category(client, "Rent", "expense")
    food = create_category(client, "Food", "expense")
    transport = create_category(client, "Transport", "expense")

    post_transaction(
        client, type="income", amount=3000, account_id=checking["id"],
        category_id=salary["id"], date=TODAY.replace(day=2).isoformat(),
    )
    for day, cat, amount in ((3, rent, 800), (4, food, 400), (6, transport, 200)):
        post_transaction(
            client, type="expense", amount=amount, account_id=checking["id"],
            category_id=cat["id"], date=TODAY.replace(day=day).isoformat(),
        )

    result = summary(session)
    assert result["income"]["current"] == 3000
    assert result["expenses"]["current"] == 1400
    assert result["savings"]["current"] == 1600
    assert result["savings"]["rate"] == round(1600 / 3000 * 100, 1)

    categories = result["categories"]
    assert [c["category_name"] for c in categories] == ["Rent", "Food", "Transport"]
    assert [c["amount"] for c in categories] == [800, 400, 200]
    for item, expected in zip(categories, (800, 400, 200)):
        assert item["share_pct"] == round(expected / 1400 * 100, 1)
    # The donut always sums to the period's expenses, and its shares to 100%.
    assert sum(c["amount"] for c in categories) == 1400
    assert round(sum(c["share_pct"] for c in categories), 1) == 100.0


# -- C: transfers never touch income, expenses or net worth ------------------


def test_scenario_c_transfer_is_fully_neutral(client, session):
    bank = create_account(client, "Bank", opening_balance=1000)
    savings = create_account(client, "Savings", opening_balance=0)
    salary = create_category(client, "Salary", "income")

    post_transaction(
        client, type="income", amount=500, account_id=bank["id"],
        category_id=salary["id"], date=TODAY.replace(day=2).isoformat(),
    )

    before_summary = summary(session)
    before_sts = safe_to_spend(session)
    before = overview(client)
    assert before_summary["income"]["current"] == 500
    assert before_summary["expenses"]["current"] == 0
    assert before["net_worth"] == 1500
    assert before_sts["available_money"] == 1500

    post_transfer(client, bank["id"], savings["id"], 400, TODAY)

    after_summary = summary(session)
    after_sts = safe_to_spend(session)
    after = overview(client)
    assert after_summary["income"]["current"] == 500
    assert after_summary["expenses"]["current"] == 0
    assert after["net_worth"] == 1500
    assert after_sts["available_money"] == 1500

    accounts = {a["name"]: a["current_balance"] for a in client.get("/api/v1/accounts").json()}
    assert accounts["Bank"] == 1100
    assert accounts["Savings"] == 400


# -- D: a credit purchase and its payment are each counted once --------------

CREDIT = date(TODAY.year, TODAY.month, 4)


def test_scenario_d_credit_purchase_and_payment_no_double_count(client, session):
    bank = create_account(client, "Bank", opening_balance=2000)
    card = create_account(client, "Card", opening_balance=0, type="credit_card")
    shopping = create_category(client, "Shopping", "expense")

    post_transaction(
        client, type="expense", amount=500, account_id=card["id"],
        category_id=shopping["id"], date=CREDIT.isoformat(),
    )

    result = summary(session)
    assert result["expenses"]["current"] == 500  # counted once
    assert result["net_worth"]["assets"] == 2000
    assert result["net_worth"]["liabilities"] == 500
    assert result["net_worth"]["net_worth"] == 1500
    assert overview(client)["net_worth"] == 1500

    # Paying the card is a transfer: net worth and expenses must not move.
    post_transfer(client, bank["id"], card["id"], 500, TODAY)

    result = summary(session)
    assert result["expenses"]["current"] == 500
    assert result["income"]["current"] == 0
    assert result["net_worth"]["assets"] == 1500
    assert result["net_worth"]["liabilities"] == 0
    assert result["net_worth"]["net_worth"] == 1500
    assert safe_to_spend(session)["available_money"] == 1500
    assert overview(client)["net_worth"] == 1500


# -- E: budgets planned / actual / remaining --------------------------------


def test_scenario_e_budget_planned_actual_remaining(client):
    checking = create_account(client, "Checking", opening_balance=0)
    food = create_category(client, "Food", "expense")
    post_transaction(
        client, type="expense", amount=300, account_id=checking["id"],
        category_id=food["id"], date=TODAY.replace(day=4).isoformat(),
    )

    put_budget(client, items=[{"category_id": food["id"], "planned_amount": 400}])

    response = client.get("/api/v1/budgets", params={"period": TODAY.isoformat()})
    assert response.status_code == 200, response.text
    result = response.json()

    assert result["totals"]["planned"] == 400
    assert result["totals"]["actual"] == 300
    assert result["totals"]["remaining"] == 100
    assert result["totals"]["pct_used"] == 75.0
    assert result["totals"]["over_budget"] is False
    row = result["items"][0]
    assert row["planned_amount"] == 400
    assert row["actual_amount"] == 300
    assert row["remaining_amount"] == 100
    assert row["pct_used"] == 75.0
    assert row["over_budget"] is False

    # Spend past the plan: remaining goes negative and the flag flips.
    post_transaction(
        client, type="expense", amount=150, account_id=checking["id"],
        category_id=food["id"], date=TODAY.replace(day=6).isoformat(),
    )
    result = client.get("/api/v1/budgets", params={"period": TODAY.isoformat()}).json()
    assert result["totals"]["actual"] == 450
    assert result["totals"]["remaining"] == -50
    assert result["totals"]["pct_used"] == 112.5
    assert result["totals"]["over_budget"] is True
    row = result["items"][0]
    assert row["over_budget"] is True
    assert row["status"] == "over"


# -- F: goal progress and deadline pacing ------------------------------------


def test_scenario_f_goal_progress_and_pacing(client):
    goal = client.post(
        "/api/v1/goals",
        json={"name": "Emergency fund", "target_amount": 5000, "current_amount": 2000},
    ).json()
    assert goal["progress_pct"] == 40.0
    assert goal["remaining_amount"] == 3000.0
    assert goal["required_monthly_saving"] is None  # no deadline yet

    deadline = months_shift(date.today(), 6)
    paced = client.post(
        "/api/v1/goals",
        json={
            "name": "Trip",
            "target_amount": 5000,
            "current_amount": 2000,
            "target_date": deadline.isoformat(),
        },
    ).json()
    assert paced["progress_pct"] == 40.0
    assert paced["remaining_amount"] == 3000.0
    assert paced["required_monthly_saving"] == 500.0  # 3000 / 6 months


# -- G: Safe-to-Spend with the full committed-pool ---------------------------

STS_TODAY = date(2026, 10, 22)  # 22nd -> 10 days left in October


def test_scenario_g_safe_to_spend_exact_pool(client, session):
    checking = create_account(client, "Checking", opening_balance=1900)
    salary = create_category(client, "Salary", "income")
    post_transaction(
        client, type="income", amount=100, account_id=checking["id"],
        category_id=salary["id"], date=date(2026, 10, 1).isoformat(),
    )

    ProfileService(session).update(preferences={"minimum_reserve": 300})
    session.commit()

    put_budget(
        client,
        allocation={"income": 0, "needs": 0, "wants": 0, "savings": 400, "other": 0},
        period=STS_TODAY,
    )
    client.post(
        "/api/v1/recurring",
        json={
            "account_id": checking["id"],
            "type": "expense",
            "amount": 800,
            "frequency": "monthly",
            "next_occurrence": "2026-10-25",
            "description": "Rent",
        },
    )

    result = safe_to_spend(session, today=STS_TODAY)
    assert result["status"] == "ok"
    assert result["available_money"] == 2000            # 1900 opening + 100 income
    assert [o["amount"] for o in result["obligations"]] == [800]
    assert result["obligations_total"] == 800
    assert result["planned_savings"] == 400
    assert result["reserve_amount"] == 300
    assert result["discretionary"] == 500               # 2000 - 800 - 400 - 300
    assert result["remaining_days"] == 10
    assert result["safe_to_spend_daily"] == 50.0        # 500 / 10


def test_scenario_g1_safe_to_spend_needs_history(client):
    create_account(client, "Checking", opening_balance=5000)
    payload = client.get("/api/v1/analytics/safe-to-spend").json()
    assert payload["status"] == "insufficient"
    assert payload["safe_to_spend_daily"] is None


# -- H: recurring records post exactly one ledger row ------------------------


def test_scenario_h_recurring_record_posts_exactly_once(client):
    checking = create_account(client, "Checking", opening_balance=0)
    due = date.today() + timedelta(days=5)

    response = client.post(
        "/api/v1/recurring",
        json={
            "account_id": checking["id"],
            "type": "expense",
            "amount": 120,
            "frequency": "monthly",
            "next_occurrence": due.isoformat(),
            "description": "Internet",
        },
    )
    assert response.status_code == 201, response.text
    template = response.json()

    # Projection is a pure read: nothing posts until record is called.
    upcoming = client.get("/api/v1/recurring/upcoming", params={"days": 30}).json()
    occurrence = [
        o for o in upcoming["occurrences"] if o["recurring_id"] == template["id"]
    ]
    assert len(occurrence) == 1
    assert occurrence[0]["due_date"] == due.isoformat()
    assert occurrence[0]["amount"] == 120
    assert occurrence[0]["overdue"] is False

    def expense_total():
        response = client.get("/api/v1/transactions/summary").json()
        return response["expense"], response["net"]

    assert expense_total() == (0, 0)

    response = client.post(f"/api/v1/recurring/{template['id']}/record")
    assert response.status_code == 200, response.text
    assert response.json()["date"] == due.isoformat()
    assert response.json()["next_occurrence"] != due.isoformat()

    assert expense_total() == (120, -120)
    accounts = {a["id"]: a["current_balance"] for a in client.get("/api/v1/accounts").json()}
    assert accounts[checking["id"]] == -120

    # Re-recording the same occurrence is rejected — and nothing doubled.
    assert (
        client.post(
            f"/api/v1/recurring/{template['id']}/record",
            params={"date": due.isoformat()},
        ).status_code
        == 400
    )
    assert expense_total() == (120, -120)

    # Arbitrary far-future dates are rejected too.
    far = date.today() + timedelta(days=120)
    assert (
        client.post(
            f"/api/v1/recurring/{template['id']}/record",
            params={"date": far.isoformat()},
        ).status_code
        == 400
    )
    assert expense_total() == (120, -120)


def test_scenario_h1_clamped_month_end_cannot_double_post(client):
    checking = create_account(client, "Checking", opening_balance=0)
    response = client.post(
        "/api/v1/recurring",
        json={
            "account_id": checking["id"],
            "type": "expense",
            "amount": 10,
            "frequency": "monthly",
            "next_occurrence": "2026-01-31",
            "description": "Clamped",
        },
    )
    assert response.status_code == 201, response.text
    template = response.json()

    # Jan 31 -> Feb 28 (clamped). After posting, the explicit date no longer
    # round-trips (previous_occurrence(Feb 28) is Jan 28), so re-posting the
    # consumed occurrence is refused instead of duplicating the ledger row.
    first = client.post(f"/api/v1/recurring/{template['id']}/record")
    assert first.status_code == 200
    assert first.json()["next_occurrence"] == "2026-02-28"
    assert (
        client.post(
            f"/api/v1/recurring/{template['id']}/record",
            params={"date": "2026-01-31"},
        ).status_code
        == 400
    )
    summary = client.get("/api/v1/transactions/summary").json()
    assert summary["expense"] == 10


# -- I: forecasts and history stay ledger-faithful ---------------------------


def seed_two_periods(client, today=TODAY) -> dict:
    checking = create_account(client, "Checking", opening_balance=500)
    salary = create_category(client, "Salary", "income")
    food = create_category(client, "Food", "expense")
    prev_day = (today.replace(day=1) - timedelta(days=1)).replace(day=2)
    post_transaction(
        client, type="income", amount=2500, account_id=checking["id"],
        category_id=salary["id"], date=prev_day.isoformat(),
    )
    post_transaction(
        client, type="expense", amount=300, account_id=checking["id"],
        category_id=food["id"], date=prev_day.isoformat(),
    )
    post_transaction(
        client, type="income", amount=3000, account_id=checking["id"],
        category_id=salary["id"], date=today.replace(day=2).isoformat(),
    )
    post_transaction(
        client, type="expense", amount=650, account_id=checking["id"],
        category_id=food["id"], date=today.replace(day=4).isoformat(),
    )
    return {"checking": checking}


def test_scenario_i_forecast_and_history_are_ledger_faithful(client, session):
    seed_two_periods(client)

    result = summary(session)
    forecasts = result["forecasts"]
    # Actuals are the ledger numbers; never modified by estimation.
    assert forecasts["income"]["actual"] == result["income"]["current"] == 3000
    assert forecasts["spending"]["actual"] == result["expenses"]["current"] == 650
    assert forecasts["income"]["is_estimate"] is True
    assert forecasts["spending"]["is_estimate"] is True
    assert forecasts["income"]["estimated"] != forecasts["income"]["actual"]
    assert isinstance(forecasts["note"], str) and forecasts["note"]

    history = result["history"]
    assert history[-1]["closed"] is False
    assert history[-1]["income"] == 3000
    assert history[-1]["expense"] == 650
    previous = history[-2]
    assert previous["closed"] is True
    assert previous["income"] == 2500
    assert previous["expense"] == 300
    # Empty windows ahead of the data carry zeros but never an invented rate.
    assert history[0]["income"] == 0
    assert history[0]["expense"] == 0
    assert history[0]["savings_rate"] is None

    assert result["net_worth_history"][-1]["net_worth"] == overview(client)["net_worth"]


# -- cross-endpoint dashboard consistency ------------------------------------


def test_dashboard_numbers_agree_across_endpoints(client):
    today = date.today()
    checking = create_account(client, "Checking", opening_balance=0)
    savings = create_account(client, "Savings", opening_balance=0)
    salary = create_category(client, "Salary", "income")
    rent = create_category(client, "Rent", "expense")

    post_transaction(
        client, type="income", amount=3000, account_id=checking["id"],
        category_id=salary["id"], date=today.isoformat(),
    )
    post_transaction(
        client, type="expense", amount=800, account_id=checking["id"],
        category_id=rent["id"], date=today.isoformat(),
    )
    post_transfer(client, checking["id"], savings["id"], 500, today)
    put_budget(client, period=today, items=[{"category_id": rent["id"], "planned_amount": 1000}])
    client.post(
        "/api/v1/debts",
        json={
            "name": "Personal loan",
            "original_amount": 500,
            "remaining_amount": 500,
        },
    )

    analytics = client.get("/api/v1/analytics").json()
    overview_payload = overview(client)
    budgets = client.get("/api/v1/budgets", params={"period": today.isoformat()}).json()
    debts = client.get("/api/v1/debts/totals").json()

    # Analytics and overview agree on assets, liabilities and net worth.
    nw = analytics["net_worth"]
    assert nw["assets"] == overview_payload["total_assets"]
    assert nw["liabilities"] == overview_payload["account_liabilities"]
    assert nw["net_worth"] == overview_payload["total_assets"] - overview_payload["account_liabilities"]
    # The unlinked debt only shows up in the debt-adjusted figure.
    assert nw["net_worth_including_debts"] == overview_payload["net_worth"]
    assert nw["net_worth_including_debts"] == nw["net_worth"] - 500
    assert overview_payload["debt_liabilities"] == 500
    assert debts["total_remaining"] == 500

    # Budget engine and dashboard feed agree number for number.
    assert analytics["budget"]["totals"] == budgets["totals"]

    # Transaction summary in the analytics window matches the dashboard exactly.
    period = analytics["period"]
    txn = client.get(
        "/api/v1/transactions/summary",
        params={"date_from": period["period_start"], "date_to": period["period_end"]},
    ).json()
    assert txn["income"] == analytics["income"]["current"] == 3000
    assert txn["expense"] == analytics["expenses"]["current"] == 800
    # The transfer is visible as volume but never as income/expense.
    assert txn["transfer_volume"] == 500
    assert txn["net"] == 2200

    # Safe-to-Spend's available pool matches account balances (no archives).
    sts = client.get("/api/v1/analytics/safe-to-spend").json()
    assert sts["status"] == "ok"
    assert sts["available_money"] == overview_payload["total_assets"] - overview_payload["account_liabilities"]
    assert sts["available_money"] == (3000 - 800 - 500) + 500