"""Transfer behaviour: validation, statuses and list merging."""

from __future__ import annotations


def setup(client):
    source = client.post("/api/v1/accounts", json={"name": "Checking", "opening_balance": 1000}).json()
    destination = client.post("/api/v1/accounts", json={"name": "Savings", "opening_balance": 100}).json()
    return source, destination


def create_transfer(client, source, destination, **payload):
    response = client.post(
        "/api/v1/transfers",
        json={
            "source_account_id": source["id"],
            "destination_account_id": destination["id"],
            "amount": 200,
            "date": "2026-10-05",
            **payload,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_transfer_moves_money(client):
    source, destination = setup(client)
    row = create_transfer(client, source, destination, description="Monthly save")
    assert row["entity"] == "transfer"
    assert row["type"] == "transfer"
    assert row["status"] == "completed"
    assert row["account_id"] == source["id"]
    assert row["destination_account_id"] == destination["id"]
    assert row["category_id"] is None

    assert client.get(f"/api/v1/accounts/{source['id']}").json()["current_balance"] == 800
    assert client.get(f"/api/v1/accounts/{destination['id']}").json()["current_balance"] == 300


def test_same_account_transfer_rejected(client):
    source, _ = setup(client)
    response = client.post(
        "/api/v1/transfers",
        json={
            "source_account_id": source["id"],
            "destination_account_id": source["id"],
            "amount": 10,
            "date": "2026-10-05",
        },
    )
    assert response.status_code == 400
    assert "different accounts" in response.json()["detail"]


def test_transfer_via_transaction_endpoint(client):
    source, destination = setup(client)
    response = client.post(
        "/api/v1/transactions",
        json={
            "type": "transfer",
            "amount": 50,
            "account_id": source["id"],
            "destination_account_id": destination["id"],
            "date": "2026-10-05",
        },
    )
    assert response.status_code == 201
    assert response.json()["entity"] == "transfer"
    assert client.get(f"/api/v1/accounts/{source['id']}").json()["current_balance"] == 950


def test_transfer_without_destination_rejected(client):
    source, _ = setup(client)
    response = client.post(
        "/api/v1/transactions",
        json={"type": "transfer", "amount": 50, "account_id": source["id"], "date": "2026-10-05"},
    )
    assert response.status_code == 400
    assert "destination" in response.json()["detail"]


def test_destination_on_plain_transaction_rejected(client):
    source, destination = setup(client)
    response = client.post(
        "/api/v1/transactions",
        json={
            "type": "expense",
            "amount": 5,
            "account_id": source["id"],
            "destination_account_id": destination["id"],
            "date": "2026-10-05",
        },
    )
    assert response.status_code == 400


def test_update_transfer(client):
    source, destination = setup(client)
    row = create_transfer(client, source, destination)
    response = client.patch(
        f"/api/v1/transfers/{row['id']}", json={"amount": 250, "description": "more"}
    )
    assert response.status_code == 200
    assert response.json()["amount"] == 250
    assert client.get(f"/api/v1/accounts/{source['id']}").json()["current_balance"] == 750


def test_update_transfer_swap_accounts(client):
    source, destination = setup(client)
    row = create_transfer(client, source, destination, amount=100)
    second = client.post("/api/v1/accounts", json={"name": "Third"}).json()
    response = client.patch(
        f"/api/v1/transfers/{row['id']}", json={"destination_account_id": second["id"]}
    )
    assert response.status_code == 200
    assert client.get(f"/api/v1/accounts/{destination['id']}").json()["current_balance"] == 100
    assert client.get(f"/api/v1/accounts/{second['id']}").json()["current_balance"] == 100


def test_delete_transfer_restores_balances(client):
    source, destination = setup(client)
    row = create_transfer(client, source, destination)
    assert client.delete(f"/api/v1/transfers/{row['id']}").status_code == 200
    assert client.get(f"/api/v1/accounts/{source['id']}").json()["current_balance"] == 1000
    assert client.get(f"/api/v1/accounts/{destination['id']}").json()["current_balance"] == 100
    assert client.get(f"/api/v1/transfers/{row['id']}").status_code == 404


def test_cancelled_transfer_excluded_from_balance(client):
    source, destination = setup(client)
    row = create_transfer(client, source, destination, status="cancelled")
    assert client.get(f"/api/v1/accounts/{source['id']}").json()["current_balance"] == 1000
    assert client.get(f"/api/v1/accounts/{destination['id']}").json()["current_balance"] == 100
    # Cancelled transfers stay visible in the list.
    items = client.get("/api/v1/transactions", params={"type": "transfer"}).json()["items"]
    assert any(item["id"] == row["id"] for item in items)


def test_bad_transfer_status_rejected(client):
    source, destination = setup(client)
    response = client.post(
        "/api/v1/transfers",
        json={
            "source_account_id": source["id"],
            "destination_account_id": destination["id"],
            "amount": 1,
            "date": "2026-10-05",
            "status": "weird",
        },
    )
    assert response.status_code == 422


def test_transfers_merge_into_transaction_list(client):
    source, destination = setup(client)
    create_transfer(client, source, destination)
    client.post(
        "/api/v1/transactions",
        json={"type": "expense", "amount": 10, "account_id": source["id"], "date": "2026-10-06"},
    )
    data = client.get("/api/v1/transactions").json()
    assert data["total"] == 2
    entities = {item["entity"] for item in data["items"]}
    assert entities == {"transaction", "transfer"}
