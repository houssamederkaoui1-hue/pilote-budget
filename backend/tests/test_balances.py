"""Balance computation: opening balances, transfers, void/cancelled exclusion.

The balance formula lives in ``BalanceService`` and is the single source of
truth; these tests pin it down end to end through the API plus a few direct
service checks.
"""

from __future__ import annotations


def create_account(client, name, **payload):
    return client.post("/api/v1/accounts", json={"name": name, **payload}).json()


def add_transaction(client, account_id, type, amount, date="2026-10-01", **payload):
    response = client.post(
        "/api/v1/transactions",
        json={"type": type, "amount": amount, "account_id": account_id, "date": date, **payload},
    )
    assert response.status_code == 201, response.text
    return response.json()


def balance(client, account_id):
    return client.get(f"/api/v1/accounts/{account_id}").json()["current_balance"]


def test_balance_formula_end_to_end(client):
    checking = create_account(client, "Checking", opening_balance=1000)
    savings = create_account(client, "Savings", opening_balance=500)

    add_transaction(client, checking["id"], "income", 2500)
    add_transaction(client, checking["id"], "expense", 42.5)
    client.post(
        "/api/v1/transfers",
        json={
            "source_account_id": checking["id"],
            "destination_account_id": savings["id"],
            "amount": 300,
            "date": "2026-10-03",
        },
    )
    client.post(
        "/api/v1/transfers",
        json={
            "source_account_id": savings["id"],
            "destination_account_id": checking["id"],
            "amount": 100,
            "date": "2026-10-04",
        },
    )

    assert balance(client, checking["id"]) == 3257.5  # 1000 + 2500 - 42.5 - 300 + 100
    assert balance(client, savings["id"]) == 700  # 500 + 300 - 100


def test_void_transaction_excluded_from_balance(client):
    account = create_account(client, "Checking", opening_balance=100)
    add_transaction(client, account["id"], "income", 999, status="void")
    assert balance(client, account["id"]) == 100
    add_transaction(client, account["id"], "income", 1, status="pending")
    assert balance(client, account["id"]) == 101  # pending still counts


def test_cancelled_transfer_excluded(client):
    source = create_account(client, "A")
    destination = create_account(client, "B")
    client.post(
        "/api/v1/transfers",
        json={
            "source_account_id": source["id"],
            "destination_account_id": destination["id"],
            "amount": 500,
            "date": "2026-10-01",
            "status": "cancelled",
        },
    )
    assert balance(client, source["id"]) == 0
    assert balance(client, destination["id"]) == 0


def test_current_balance_cache_matches_computed(session):
    from app.services.account_service import AccountService
    from app.services.balance_service import BalanceService
    from app.services.transaction_service import TransactionService

    accounts = AccountService(session)
    account = accounts.create(name="Cache Check", opening_balance=100)
    TransactionService(session).create(
        type="expense", amount=30, account_id=account.id, date="2026-10-01"
    )
    session.commit()

    cached = accounts.get(account.id).current_balance
    computed = BalanceService(session).compute(account.id)
    assert cached == computed == 70


def test_summary_excludes_transfers(client):
    account = create_account(client, "Checking")
    add_transaction(client, account["id"], "income", 2500)
    add_transaction(client, account["id"], "expense", 500)
    destination = create_account(client, "Savings")
    client.post(
        "/api/v1/transfers",
        json={
            "source_account_id": account["id"],
            "destination_account_id": destination["id"],
            "amount": 1000,
            "date": "2026-10-05",
        },
    )

    summary = client.get("/api/v1/transactions/summary").json()
    assert summary["income"] == 2500
    assert summary["expense"] == 500
    assert summary["net"] == 2000
    assert summary["transfer_volume"] == 1000  # reported but never summed in


def test_summary_date_filters(client):
    account = create_account(client, "Checking")
    add_transaction(client, account["id"], "income", 100, date="2026-09-15")
    add_transaction(client, account["id"], "income", 200, date="2026-10-15")

    october = client.get(
        "/api/v1/transactions/summary",
        params={"date_from": "2026-10-01", "date_to": "2026-10-31"},
    ).json()
    assert october["income"] == 200
    assert october["expense"] == 0

    september = client.get(
        "/api/v1/transactions/summary", params={"date_to": "2026-09-30"}
    ).json()
    assert september["income"] == 100


def test_opening_balance_update_recomputes(session):
    from app.services.account_service import AccountService

    accounts = AccountService(session)
    account = accounts.create(name="Seed", opening_balance=10)
    accounts.update(account.id, opening_balance=500)
    session.commit()
    assert accounts.get(account.id).current_balance == 500
