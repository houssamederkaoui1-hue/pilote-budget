"""Financial overview: assets, liabilities, net worth (no double counting).

Net worth rule: assets = sum of positive account balances; liabilities =
sum of negative account balances plus debts, where a debt linked to a
liability account contributes only the part NOT already covered by that
account's balance.
"""

from __future__ import annotations

from datetime import date, timedelta


def create_account(client, name, **payload):
    return client.post("/api/v1/accounts", json={"name": name, **payload}).json()


def create_debt(client, **payload):
    return client.post("/api/v1/debts", json=payload).json()


def overview(client):
    response = client.get("/api/v1/overview")
    assert response.status_code == 200, response.text
    return response.json()


def test_net_worth_from_account_balances(client):
    create_account(client, "Checking", opening_balance=1000)
    create_account(client, "Savings", opening_balance=500)
    create_account(client, "Credit Card", opening_balance=-300)

    result = overview(client)
    assert result["total_assets"] == 1500
    assert result["account_liabilities"] == 300
    assert result["debt_liabilities"] == 0
    assert result["total_liabilities"] == 300
    assert result["net_worth"] == 1200


def test_linked_debt_does_not_double_count(client):
    card = create_account(client, "Credit Card", opening_balance=-300)
    create_account(client, "Checking", opening_balance=1500)
    create_debt(client, name="Card Debt", original_amount=250, remaining_amount=250, account_id=card["id"])

    result = overview(client)
    assert result["debt_liabilities"] == 0  # fully covered by the account balance
    assert result["total_liabilities"] == 300
    assert result["net_worth"] == 1200


def test_uncovered_part_of_linked_debt_counts(client):
    card = create_account(client, "Credit Card", opening_balance=-300)
    create_account(client, "Checking", opening_balance=1500)
    create_debt(client, name="Loan", original_amount=400, remaining_amount=400, account_id=card["id"])

    result = overview(client)
    assert result["account_liabilities"] == 300
    assert result["debt_liabilities"] == 100  # 400 remaining − 300 covered
    assert result["total_liabilities"] == 400
    assert result["net_worth"] == 1100


def test_unlinked_debt_adds_full_balance(client):
    create_account(client, "Checking", opening_balance=1500)
    card = create_account(client, "Credit Card", opening_balance=-300)
    create_debt(client, name="Student Loan", original_amount=400, remaining_amount=400, account_id=card["id"])
    create_debt(client, name="Personal Debt", original_amount=500, remaining_amount=500)

    result = overview(client)
    assert result["account_liabilities"] == 300
    assert result["debt_liabilities"] == 100 + 500
    assert result["total_liabilities"] == 900
    assert result["net_worth"] == 600


def test_income_and_expense_moves_net_worth(client):
    account = create_account(client, "Checking", opening_balance=100)
    response = client.post(
        "/api/v1/transactions",
        json={
            "type": "income",
            "amount": 2500,
            "account_id": account["id"],
            "date": date.today().isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    assert overview(client)["net_worth"] == 2600

    response = client.post(
        "/api/v1/transactions",
        json={
            "type": "expense",
            "amount": 400,
            "account_id": account["id"],
            "date": date.today().isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    assert overview(client)["net_worth"] == 2200


def test_archived_accounts_still_count(client):
    account = create_account(client, "Old Savings", opening_balance=900)
    client.patch(f"/api/v1/accounts/{account['id']}", json={"active": False})
    result = overview(client)
    assert result["total_assets"] == 900


def test_transfer_is_net_worth_neutral(client):
    checking = create_account(client, "Checking", opening_balance=1000)
    savings = create_account(client, "Savings")
    response = client.post(
        "/api/v1/transfers",
        json={
            "source_account_id": checking["id"],
            "destination_account_id": savings["id"],
            "amount": 300,
            "date": date.today().isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    assert overview(client)["net_worth"] == 1000