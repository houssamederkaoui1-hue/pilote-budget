"""Debt tracking: CRUD, roll-ups and upcoming due dates."""

from __future__ import annotations

from datetime import date, timedelta


def create_account(client, name, **payload):
    return client.post("/api/v1/accounts", json={"name": name, **payload}).json()


def create_debt(client, **payload):
    return client.post("/api/v1/debts", json=payload).json()


def totals(client):
    response = client.get("/api/v1/debts/totals")
    assert response.status_code == 200, response.text
    return response.json()


def test_crud_roundtrip(client):
    debt = create_debt(
        client,
        name="Car Loan",
        creditor="ABC Bank",
        original_amount=10000,
        remaining_amount=8000,
        interest_rate=4.5,
        minimum_payment=300,
        due_date=(date.today() + timedelta(days=10)).isoformat(),
    )
    assert debt["remaining_amount"] == 8000
    assert debt["account_name"] is None

    response = client.patch(f"/api/v1/debts/{debt['id']}", json={"remaining_amount": 7500})
    assert response.status_code == 200, response.text
    assert response.json()["remaining_amount"] == 7500

    listed = client.get("/api/v1/debts").json()
    assert len(listed) == 1 and listed[0]["id"] == debt["id"]

    assert client.delete(f"/api/v1/debts/{debt['id']}").status_code == 200
    assert client.get("/api/v1/debts").json() == []


def test_totals_active_only_and_ordering(client):
    due_soon = (date.today() + timedelta(days=2)).isoformat()
    due_late = (date.today() + timedelta(days=10)).isoformat()
    create_debt(client, name="Card", original_amount=5000, remaining_amount=2000, minimum_payment=100, due_date=due_late)
    create_debt(client, name="Loan", original_amount=10000, remaining_amount=8000, minimum_payment=300, due_date=due_soon)
    create_debt(client, name="Legacy", original_amount=7000, remaining_amount=7000, minimum_payment=200, due_date=due_soon, active=False)
    create_debt(client, name="No due date", original_amount=100, remaining_amount=100, minimum_payment=50)

    result = totals(client)
    assert result["total_original"] == 15100  # active only (excludes Legacy)
    assert result["total_remaining"] == 10100
    assert result["total_minimum_payment"] == 450
    assert result["active_debt_count"] == 3
    assert [item["name"] for item in result["upcoming_due_dates"]] == ["Loan", "Card"]
    assert result["upcoming_due_dates"][0]["due_date"] == due_soon


def test_remaining_cannot_exceed_original(client):
    response = client.post(
        "/api/v1/debts",
        json={"name": "Bad", "original_amount": 1000, "remaining_amount": 1200},
    )
    assert response.status_code == 400
    assert "cannot exceed" in response.json()["detail"]


def test_reduces_original_validates_remaining(client):
    debt = create_debt(client, name="Loan", original_amount=1000, remaining_amount=900)
    response = client.patch(f"/api/v1/debts/{debt['id']}", json={"original_amount": 800})
    assert response.status_code == 400


def test_validation_rules(client):
    assert client.post("/api/v1/debts", json={"name": "", "original_amount": 100}).status_code == 400
    assert client.post("/api/v1/debts", json={"name": "X", "original_amount": -1}).status_code == 422
    assert client.post("/api/v1/debts", json={"name": "X", "original_amount": 100, "interest_rate": -1}).status_code == 422
    assert client.get("/api/v1/debts/999999").status_code == 404
    assert client.get("/api/v1/debts/totals").json()["active_debt_count"] == 0


def test_account_link(client):
    account = create_account(client, "Credit Card")
    debt = create_debt(client, name="Card Debt", original_amount=500, remaining_amount=400, account_id=account["id"])
    assert debt["account_name"] == "Credit Card"