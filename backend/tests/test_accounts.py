"""Account CRUD, conflicts and balance projection."""

from __future__ import annotations


def create_account(client, name="Main", **payload):
    response = client.post("/api/v1/accounts", json={"name": name, **payload})
    assert response.status_code == 201, response.text
    return response.json()


def test_create_and_get_account(client):
    account = create_account(client, "Checking", opening_balance=1250.75, type="checking")
    assert account["type"] == "checking"
    assert account["opening_balance"] == 1250.75
    assert account["current_balance"] == 1250.75
    assert account["active"] is True

    fetched = client.get(f"/api/v1/accounts/{account['id']}").json()
    assert fetched["name"] == "Checking"


def test_create_requires_name(client):
    response = client.post("/api/v1/accounts", json={"name": "  "})
    # Empty after trimming fails in the service (400); blank via schema passes min_length.
    assert response.status_code in (400, 422)


def test_duplicate_name_conflicts(client):
    create_account(client, "Wallet")
    response = client.post("/api/v1/accounts", json={"name": "wallet"})
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


def test_unknown_account_type_rejected(client):
    response = client.post("/api/v1/accounts", json={"name": "X", "type": "bitcoin"})
    assert response.status_code == 422  # schema-level enum validation


def test_update_account(client):
    account = create_account(client, "Savings")
    response = client.patch(
        f"/api/v1/accounts/{account['id']}",
        json={"name": "Rainy Day", "opening_balance": 200, "description": "buffer"},
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["name"] == "Rainy Day"
    assert updated["opening_balance"] == 200
    assert updated["current_balance"] == 200


def test_archive_hides_from_default_list(client):
    account = create_account(client, "Old Bank")
    response = client.post(f"/api/v1/accounts/{account['id']}/archive")
    assert response.json()["active"] is False

    active = client.get("/api/v1/accounts").json()
    assert account["id"] not in [row["id"] for row in active]

    with_archived = client.get("/api/v1/accounts", params={"include_archived": True}).json()
    assert account["id"] in [row["id"] for row in with_archived]

    client.post(f"/api/v1/accounts/{account['id']}/activate")
    assert account["id"] in [row["id"] for row in client.get("/api/v1/accounts").json()]


def test_delete_unused_account(client):
    account = create_account(client, "Temp")
    response = client.delete(f"/api/v1/accounts/{account['id']}")
    assert response.status_code == 200
    assert client.get(f"/api/v1/accounts/{account['id']}").status_code == 404


def test_delete_referenced_account_conflicts(client):
    account = create_account(client, "Busy")
    client.post(
        "/api/v1/transactions",
        json={"type": "expense", "amount": 5, "account_id": account["id"], "date": "2026-10-01"},
    )
    response = client.delete(f"/api/v1/accounts/{account['id']}")
    assert response.status_code == 409
    assert "archive" in response.json()["detail"]


def test_delete_account_referenced_by_transfer_conflicts(client):
    source = create_account(client, "Source")
    destination = create_account(client, "Destination")
    client.post(
        "/api/v1/transfers",
        json={
            "source_account_id": source["id"],
            "destination_account_id": destination["id"],
            "amount": 10,
            "date": "2026-10-01",
        },
    )
    assert client.delete(f"/api/v1/accounts/{source['id']}").status_code == 409


def test_filter_accounts_by_type(client):
    create_account(client, "Bank One", type="bank")
    create_account(client, "Cash Pocket", type="cash")
    banks = client.get("/api/v1/accounts", params={"type": "bank"}).json()
    assert [row["name"] for row in banks] == ["Bank One"]
    assert client.get("/api/v1/accounts", params={"type": "nope"}).status_code == 400


def test_unknown_account_404(client):
    assert client.get("/api/v1/accounts/999").status_code == 404
