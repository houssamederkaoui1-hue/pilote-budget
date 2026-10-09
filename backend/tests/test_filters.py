"""Merged list filtering, pagination and CSV export."""

from __future__ import annotations


def setup(client):
    checking = client.post(
        "/api/v1/accounts", json={"name": "Checking", "opening_balance": 5000}
    ).json()
    savings = client.post("/api/v1/accounts", json={"name": "Savings"}).json()
    categories = client.get("/api/v1/categories").json()
    food = next(row for row in categories if row["name"] == "Food")
    salary = next(row for row in categories if row["name"] == "Salary")

    rows = [
        # income
        client.post(
            "/api/v1/transactions",
            json={
                "type": "income",
                "amount": 3000,
                "account_id": checking["id"],
                "category_id": salary["id"],
                "date": "2026-09-01",
                "description": "September salary",
            },
        ).json(),
        # expense
        client.post(
            "/api/v1/transactions",
            json={
                "type": "expense",
                "amount": 45.2,
                "account_id": checking["id"],
                "category_id": food["id"],
                "date": "2026-10-02",
                "description": "Groceries at Lidl",
            },
        ).json(),
        # second expense, other account
        client.post(
            "/api/v1/transactions",
            json={
                "type": "expense",
                "amount": 15,
                "account_id": savings["id"],
                "date": "2026-10-03",
                "description": "Bank fee",
                "notes": "monthly charge",
            },
        ).json(),
        # transfer
        client.post(
            "/api/v1/transfers",
            json={
                "source_account_id": checking["id"],
                "destination_account_id": savings["id"],
                "amount": 500,
                "date": "2026-10-04",
                "description": "Move to savings",
            },
        ).json(),
    ]
    return checking, savings, food, rows


def test_default_list_is_sorted_newest_first(client):
    _, _, _, rows = setup(client)
    items = client.get("/api/v1/transactions").json()["items"]
    dates = [item["date"] for item in items]
    assert dates == sorted(dates, reverse=True)
    assert len(items) == 4


def test_filter_by_type(client):
    setup(client)
    transfers = client.get("/api/v1/transactions", params={"type": "transfer"}).json()
    assert transfers["total"] == 1
    assert transfers["items"][0]["entity"] == "transfer"

    expenses = client.get("/api/v1/transactions", params={"type": "expense"}).json()
    assert expenses["total"] == 2
    assert all(item["type"] == "expense" for item in expenses["items"])


def test_invalid_type_filter_is_400(client):
    setup(client)
    response = client.get("/api/v1/transactions", params={"type": "salary"})
    assert response.status_code == 400


def test_filter_by_account_includes_transfer_destination(client):
    checking, savings, _, _ = setup(client)
    checking_rows = client.get(
        "/api/v1/transactions", params={"account_id": checking["id"]}
    ).json()
    # 2 transactions + outgoing transfer
    assert checking_rows["total"] == 3

    savings_rows = client.get(
        "/api/v1/transactions", params={"account_id": savings["id"]}
    ).json()
    # 1 transaction + incoming transfer
    assert savings_rows["total"] == 2


def test_filter_by_category_excludes_transfers(client):
    _, _, food, _ = setup(client)
    food_rows = client.get(
        "/api/v1/transactions", params={"category_id": food["id"]}
    ).json()
    assert food_rows["total"] == 1
    assert food_rows["items"][0]["description"] == "Groceries at Lidl"


def test_filter_by_date_range(client):
    setup(client)
    october = client.get(
        "/api/v1/transactions",
        params={"date_from": "2026-10-01", "date_to": "2026-10-31"},
    ).json()
    assert october["total"] == 3

    empty = client.get(
        "/api/v1/transactions", params={"date_from": "2027-01-01"}
    ).json()
    assert empty["total"] == 0


def test_inverted_date_range_is_400(client):
    setup(client)
    response = client.get(
        "/api/v1/transactions",
        params={"date_from": "2026-11-01", "date_to": "2026-10-01"},
    )
    assert response.status_code == 400


def test_search_matches_description_and_notes(client):
    setup(client)
    by_description = client.get("/api/v1/transactions", params={"q": "lidl"}).json()
    assert by_description["total"] == 1

    by_notes = client.get("/api/v1/transactions", params={"q": "monthly"}).json()
    assert by_notes["total"] == 1

    none = client.get("/api/v1/transactions", params={"q": "nomatch"}).json()
    assert none["total"] == 0


def test_pagination(client):
    setup(client)
    page = client.get("/api/v1/transactions", params={"limit": 2, "offset": 0}).json()
    assert len(page["items"]) == 2
    assert page["total"] == 4
    assert page["limit"] == 2

    second_page = client.get(
        "/api/v1/transactions", params={"limit": 2, "offset": 2}
    ).json()
    assert len(second_page["items"]) == 2
    # Ids are only unique per entity (transactions and transfers have their
    # own sequences), so compare composite keys.
    first_keys = {(item["entity"], item["id"]) for item in page["items"]}
    second_keys = {(item["entity"], item["id"]) for item in second_page["items"]}
    assert not first_keys & second_keys


def test_export_csv_respects_filters(client):
    setup(client)
    response = client.get("/api/v1/transactions/export.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    body = response.text
    assert "entity,date,type,amount" in body
    assert body.count("\n") >= 5  # header + 4 rows

    filtered = client.get(
        "/api/v1/transactions/export.csv", params={"type": "transfer"}
    ).text
    assert filtered.count("\n") == 2  # header + 1 transfer
    assert "Move to savings" in filtered
    assert "Groceries" not in filtered


def test_list_row_shape_is_uniform(client):
    _, _, _, _ = setup(client)
    items = client.get("/api/v1/transactions").json()["items"]
    expected_keys = {
        "id",
        "entity",
        "type",
        "amount",
        "date",
        "description",
        "notes",
        "status",
        "account_id",
        "account_name",
        "category_id",
        "category_name",
        "destination_account_id",
        "destination_account_name",
        "created_at",
        "updated_at",
    }
    for item in items:
        assert set(item) == expected_keys
