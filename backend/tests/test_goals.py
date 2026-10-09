"""Goal projections: progress, remaining, pacing and completion estimates."""

from __future__ import annotations

from datetime import date, timedelta

from app.domain.schedules import months_shift


def create_account(client, name, **payload):
    return client.post("/api/v1/accounts", json={"name": name, **payload}).json()


def create_goal(client, **payload):
    return client.post("/api/v1/goals", json=payload).json()


def add_transaction(client, account_id, type, amount, day, **payload):
    response = client.post(
        "/api/v1/transactions",
        json={"type": type, "amount": amount, "account_id": account_id, "date": day.isoformat(), **payload},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_progress_and_remaining(client):
    goal = create_goal(client, name="New Car", target_amount=1000, current_amount=250)
    assert goal["progress_pct"] == 25.0
    assert goal["remaining_amount"] == 750.0
    assert goal["required_monthly_saving"] is None  # no deadline
    assert goal["monthly_contribution"] is None
    assert goal["estimated_completion_date"] is None


def test_required_monthly_saving(client):
    today = date.today()
    target_date = months_shift(today, 3)
    goal = create_goal(
        client, name="Trip", target_amount=1200, current_amount=0, target_date=target_date.isoformat()
    )
    assert goal["required_monthly_saving"] == 400.0


def test_no_remaining_gives_zero_pacing(client):
    today = date.today()
    goal = create_goal(
        client,
        name="Done",
        target_amount=500,
        current_amount=600,
        target_date=months_shift(today, 1).isoformat(),
    )
    assert goal["remaining_amount"] == 0.0
    assert goal["progress_pct"] == 120.0
    assert goal["required_monthly_saving"] == 0.0
    assert goal["estimated_completion_date"] == today.isoformat()


def test_contribution_rate_and_estimated_completion(client):
    today = date.today()
    account = create_account(client, "Checking")
    last_start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    last_end = today.replace(day=1) - timedelta(days=1)
    add_transaction(client, account["id"], "income", 1000, last_start + timedelta(days=2))
    add_transaction(client, account["id"], "expense", 500, last_start + timedelta(days=3))

    goal = create_goal(client, name="Kitchen", target_amount=2000, current_amount=0)
    assert goal["monthly_contribution"] == 500.0
    assert goal["estimated_completion_date"] == months_shift(today, 4).isoformat()


def test_deposit_updates_progress(client):
    goal = create_goal(client, name="Kitchen", target_amount=2000)
    response = client.patch(
        f"/api/v1/goals/{goal['id']}", json={"current_amount": 500}
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["progress_pct"] == 25.0
    assert updated["remaining_amount"] == 1500.0


def test_active_flag_and_list_order(client):
    active = create_goal(client, name="Active", target_amount=100)
    create_goal(client, name="Paused", target_amount=100, active=False)
    response = client.get("/api/v1/goals")
    assert response.status_code == 200
    goals = response.json()
    assert goals[0]["id"] == active["id"]  # active first

    merged = {goal["name"]: goal for goal in goals}
    assert merged["Paused"]["active"] is False


def test_create_requires_name_and_positive_target(client):
    assert client.post("/api/v1/goals", json={"name": "", "target_amount": 100}).status_code == 400
    assert client.post("/api/v1/goals", json={"name": "X", "target_amount": 0}).status_code == 422
    assert client.post("/api/v1/goals", json={"name": "X", "target_amount": -5}).status_code == 422


def test_account_link(client):
    account = create_account(client, "Savings")
    goal = create_goal(client, name="Funds", target_amount=500, account_id=account["id"])
    assert goal["account_name"] == "Savings"


def test_missing_goal_404(client):
    assert client.get("/api/v1/goals/999999").status_code == 404
    assert client.patch("/api/v1/goals/999999", json={"active": False}).status_code == 404


def test_delete(client):
    goal = create_goal(client, name="Gone", target_amount=50)
    response = client.delete(f"/api/v1/goals/{goal['id']}")
    assert response.status_code == 200
    assert client.get("/api/v1/goals").json() == []