"""Category CRUD, seeds, hierarchy guards and usage conflicts."""

from __future__ import annotations


def create_category(client, name, type="expense", **payload):
    response = client.post(
        "/api/v1/categories", json={"name": name, "type": type, **payload}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_default_categories_seeded(client):
    categories = client.get("/api/v1/categories").json()
    names = {(row["name"], row["type"]) for row in categories}
    assert len(categories) == 14
    assert ("Housing", "expense") in names
    assert ("Salary", "income") in names
    # Seeding is idempotent.
    assert len(client.get("/api/v1/categories").json()) == 14


def test_create_and_update_category(client):
    category = create_category(client, "Pets")
    response = client.patch(
        f"/api/v1/categories/{category['id']}", json={"description": "vet & food"}
    )
    assert response.json()["description"] == "vet & food"


def test_duplicate_name_same_type_conflicts(client):
    create_category(client, "Gym")
    response = client.post("/api/v1/categories", json={"name": "gym", "type": "expense"})
    assert response.status_code == 409


def test_same_name_other_type_allowed(client):
    create_category(client, "Bonus", type="income")
    other = create_category(client, "Bonus", type="expense")
    assert other["type"] == "expense"


def test_type_change_blocked_when_in_use(client):
    account = client.post("/api/v1/accounts", json={"name": "A"}).json()
    category = create_category(client, "Used")
    client.post(
        "/api/v1/transactions",
        json={
            "type": "expense",
            "amount": 1,
            "account_id": account["id"],
            "category_id": category["id"],
            "date": "2026-10-01",
        },
    )
    response = client.patch(
        f"/api/v1/categories/{category['id']}", json={"type": "income"}
    )
    assert response.status_code == 409


def test_delete_used_category_conflicts(client):
    account = client.post("/api/v1/accounts", json={"name": "A"}).json()
    category = create_category(client, "In Use")
    client.post(
        "/api/v1/transactions",
        json={
            "type": "expense",
            "amount": 1,
            "account_id": account["id"],
            "category_id": category["id"],
            "date": "2026-10-01",
        },
    )
    response = client.delete(f"/api/v1/categories/{category['id']}")
    assert response.status_code == 409


def test_delete_unused_category_reparents_children(client):
    parent = create_category(client, "Parent")
    child = create_category(client, "Child", parent_id=parent["id"])
    assert client.delete(f"/api/v1/categories/{parent['id']}").status_code == 200
    reloaded = client.get(f"/api/v1/categories/{child['id']}").json()
    assert reloaded["parent_id"] is None


def test_parent_cycle_rejected(client):
    parent = create_category(client, "Top")
    child = create_category(client, "Sub", parent_id=parent["id"])
    response = client.patch(
        f"/api/v1/categories/{parent['id']}", json={"parent_id": child["id"]}
    )
    assert response.status_code == 400


def test_parent_must_match_type(client):
    income_parent = create_category(client, "Earn", type="income")
    response = client.post(
        "/api/v1/categories",
        json={"name": "Spend", "type": "expense", "parent_id": income_parent["id"]},
    )
    assert response.status_code == 400


def test_archive_category(client):
    category = create_category(client, "Old One")
    client.post(f"/api/v1/categories/{category['id']}/archive")
    active = client.get("/api/v1/categories").json()
    assert category["id"] not in [row["id"] for row in active]
    archived = client.get(
        "/api/v1/categories", params={"include_archived": True}
    ).json()
    assert category["id"] in [row["id"] for row in archived]


def test_filter_categories_by_type(client):
    create_category(client, "Earned", type="income")
    income = client.get("/api/v1/categories", params={"type": "income"}).json()
    assert "Earned" in [row["name"] for row in income]
    assert all(row["type"] == "income" for row in income)


def test_unknown_category_404(client):
    assert client.get("/api/v1/categories/999").status_code == 404
