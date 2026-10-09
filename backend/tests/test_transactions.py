"""Transaction create/update/delete and validation rules."""

from __future__ import annotations

from datetime import date


def setup_account_and_categories(client):
    account = client.post(
        "/api/v1/accounts", json={"name": "Checking", "opening_balance": 100}
    ).json()
    categories = client.get("/api/v1/categories").json()
    expense = next(row for row in categories if row["type"] == "expense")
    income = next(row for row in categories if row["type"] == "income")
    return account, expense, income


def create_transaction(client, **payload):
    response = client.post("/api/v1/transactions", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_income_and_expense(client):
    account, expense, income = setup_account_and_categories(client)
    row = create_transaction(
        client,
        type="income",
        amount=2500,
        account_id=account["id"],
        category_id=income["id"],
        date="2026-10-01",
        description="Salary",
    )
    assert row["type"] == "income"
    assert row["entity"] == "transaction"
    assert row["account_name"] == "Checking"
    assert row["category_name"] == income["name"]
    assert row["date"] == "2026-10-01"

    expense_row = create_transaction(
        client,
        type="expense",
        amount=9.99,
        account_id=account["id"],
        category_id=expense["id"],
        date="2026-10-02",
    )
    assert expense_row["type"] == "expense"
    assert expense_row["amount"] == 9.99


def test_amount_must_be_positive(client):
    account, _, _ = setup_account_and_categories(client)
    response = client.post(
        "/api/v1/transactions",
        json={"type": "expense", "amount": -5, "account_id": account["id"], "date": "2026-10-01"},
    )
    assert response.status_code == 422


def test_unknown_account_is_404(client):
    response = client.post(
        "/api/v1/transactions",
        json={"type": "expense", "amount": 5, "account_id": 999, "date": "2026-10-01"},
    )
    assert response.status_code == 404


def test_unknown_category_is_404(client):
    account, _, _ = setup_account_and_categories(client)
    response = client.post(
        "/api/v1/transactions",
        json={
            "type": "expense",
            "amount": 5,
            "account_id": account["id"],
            "category_id": 999,
            "date": "2026-10-01",
        },
    )
    assert response.status_code == 404


def test_category_type_must_match(client):
    account, expense, income = setup_account_and_categories(client)
    response = client.post(
        "/api/v1/transactions",
        json={
            "type": "expense",
            "amount": 5,
            "account_id": account["id"],
            "category_id": income["id"],
            "date": "2026-10-01",
        },
    )
    assert response.status_code == 400
    assert "category" in response.json()["detail"].lower()


def test_category_optional(client):
    account, _, _ = setup_account_and_categories(client)
    row = create_transaction(
        client, type="expense", amount=5, account_id=account["id"], date="2026-10-01"
    )
    assert row["category_id"] is None


def test_update_transaction(client):
    account, expense, _ = setup_account_and_categories(client)
    row = create_transaction(
        client,
        type="expense",
        amount=10,
        account_id=account["id"],
        category_id=expense["id"],
        date="2026-10-01",
        description="Seed",
    )
    response = client.patch(
        f"/api/v1/transactions/{row['id']}",
        json={"amount": 12.5, "description": "Edited", "status": "pending"},
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["amount"] == 12.5
    assert updated["description"] == "Edited"
    assert updated["status"] == "pending"


def test_type_is_immutable(client):
    account, expense, _ = setup_account_and_categories(client)
    row = create_transaction(
        client,
        type="expense",
        amount=10,
        account_id=account["id"],
        date="2026-10-01",
    )
    response = client.patch(f"/api/v1/transactions/{row['id']}", json={"type": "income"})
    assert response.status_code == 400
    assert "cannot be changed" in response.json()["detail"]


def test_change_account_moves_balance(client):
    first = client.post("/api/v1/accounts", json={"name": "One"}).json()
    second = client.post("/api/v1/accounts", json={"name": "Two"}).json()
    row = create_transaction(
        client, type="expense", amount=40, account_id=first["id"], date="2026-10-01"
    )
    client.patch(f"/api/v1/transactions/{row['id']}", json={"account_id": second["id"]})
    assert client.get(f"/api/v1/accounts/{first['id']}").json()["current_balance"] == 0
    assert client.get(f"/api/v1/accounts/{second['id']}").json()["current_balance"] == -40


def test_delete_transaction(client):
    account, _, _ = setup_account_and_categories(client)
    row = create_transaction(
        client, type="income", amount=77, account_id=account["id"], date="2026-10-01"
    )
    assert client.get(f"/api/v1/accounts/{account['id']}").json()["current_balance"] == 177
    assert client.delete(f"/api/v1/transactions/{row['id']}").status_code == 200
    assert client.get(f"/api/v1/transactions/{row['id']}").status_code == 404
    assert client.get(f"/api/v1/accounts/{account['id']}").json()["current_balance"] == 100


def test_get_transaction_detail(client):
    account, expense, _ = setup_account_and_categories(client)
    row = create_transaction(
        client,
        type="expense",
        amount=5,
        account_id=account["id"],
        category_id=expense["id"],
        date="2026-10-01",
        notes="lunch",
    )
    fetched = client.get(f"/api/v1/transactions/{row['id']}").json()
    assert fetched["notes"] == "lunch"
    assert fetched["entity"] == "transaction"


def test_invalid_date_rejected_by_schema(client):
    account, _, _ = setup_account_and_categories(client)
    response = client.post(
        "/api/v1/transactions",
        json={"type": "expense", "amount": 5, "account_id": account["id"], "date": "not-a-date"},
    )
    assert response.status_code == 422


def test_list_paginates_and_counts_in_sql(client):
    account, expense, _ = setup_account_and_categories(client)
    destination = client.post(
        "/api/v1/accounts", json={"name": "Savings", "opening_balance": 0}
    ).json()
    for day in range(4, 9):  # 2026-10-04 .. 2026-10-08
        create_transaction(
            client,
            type="expense",
            amount=float(day),
            account_id=account["id"],
            category_id=expense["id"],
            date=f"2026-10-{day:02d}",
            description=f"Day {day}",
        )
    transfer = client.post(
        "/api/v1/transactions",
        json={
            "type": "transfer",
            "amount": 30,
            "account_id": account["id"],
            "destination_account_id": destination["id"],
            "date": "2026-10-06",
        },
    )
    assert transfer.status_code == 201

    page_one = client.get("/api/v1/transactions", params={"limit": 4, "offset": 0}).json()
    assert page_one["total"] == 6  # 5 expenses + 1 transfer
    assert len(page_one["items"]) == 4

    page_two = client.get("/api/v1/transactions", params={"limit": 4, "offset": 4}).json()
    assert len(page_two["items"]) == 2

    # Combined rows sort by date descending; transfers participate in the page.
    dates = [row["date"] for row in page_one["items"]]
    assert dates == sorted(dates, reverse=True)
    entities = {row["entity"] for row in page_one["items"]}
    assert "transfer" in entities

    # Offset/length tabs do not overlap and cover everything. ids are only
    # unique per entity (transactions and transfers have separate sequences).
    keys_one = {(row["entity"], row["id"]) for row in page_one["items"]}
    keys_two = {(row["entity"], row["id"]) for row in page_two["items"]}
    assert not (keys_one & keys_two)
    assert len(keys_one | keys_two) == page_one["total"]

    # A narrow slice still reports the full total.
    one_row = client.get("/api/v1/transactions", params={"limit": 1, "offset": 2}).json()
    assert one_row["total"] == 6
    assert len(one_row["items"]) == 1

    # type=transfer only counts and pages transfers.
    only_transfers = client.get(
        "/api/v1/transactions", params={"type": "transfer", "limit": 100}
    ).json()
    assert only_transfers["total"] == 1
    assert all(row["entity"] == "transfer" for row in only_transfers["items"])
