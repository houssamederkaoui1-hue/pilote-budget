"""CSV import: inspection, mapping, preview, commit and idempotency."""

from __future__ import annotations

import io
import json

BANK_CSV = b"""Date,Description,Amount,Category,Account,Reference
2026-09-01,Rent payment,-1200.00,Housing,Checking,REF-001
2026-09-02,Coffee,-3.50,Food,Checking,REF-002
2026-09-03,Salary,3000.00,Salary,Checking,REF-003
2026-09-04,Broken row,not-a-number,Food,Checking,REF-004
"""

SEMICOLON_CSV = b"Booking Date;Payee;Debit Amount;Credit Amount\n01.09.2026;Rewe;12,34;\n02.09.2026;Gehalt;;1500,50\n"


def upload(client, endpoint, data, filename="bank.csv", mapping=None, **form):
    files = {"file": (filename, data, "text/csv")}
    payload = dict(form)
    if mapping is not None:
        payload["mapping"] = json.dumps(mapping) if not isinstance(mapping, str) else mapping
    return client.post(f"/api/v1/imports/{endpoint}", files=files, data=payload)


def full_mapping(**options):
    columns = {"date": 0, "description": 1, "amount": 2, "category": 3, "account": 4, "reference": 5}
    return {
        "fields": {name: {"column": index} for name, index in columns.items()},
        "options": {"filename": "bank.csv", **options},
    }


def setup_account(client):
    return client.post(
        "/api/v1/accounts", json={"name": "Checking", "opening_balance": 100}
    ).json()


# -- inspect -----------------------------------------------------------------


def test_inspect_suggests_columns(client):
    response = upload(client, "inspect", BANK_CSV)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["columns"] == [
        "Date",
        "Description",
        "Amount",
        "Category",
        "Account",
        "Reference",
    ]
    assert result["row_count"] == 4
    assert result["delimiter"] == ","
    assert result["encoding"].startswith("utf-8")
    suggestions = result["suggestions"]
    assert suggestions["date"]["column"] == 0
    assert suggestions["description"]["column"] == 1
    assert suggestions["amount"]["column"] == 2
    assert suggestions["category"]["column"] == 3
    assert suggestions["account"]["column"] == 4
    assert suggestions["reference"]["column"] == 5
    assert suggestions["date"]["format"] == "%Y-%m-%d"
    assert result["sample_rows"][0][1] == "Rent payment"


def test_inspect_semicolon_debit_credit(client):
    response = upload(client, "inspect", SEMICOLON_CSV, filename="eu.csv")
    result = response.json()
    assert result["delimiter"] == ";"
    suggestions = result["suggestions"]
    assert suggestions["debit"]["column"] == 2
    assert suggestions["credit"]["column"] == 3
    assert suggestions["amount"] is None  # split wins over a single amount column
    assert suggestions["date"]["format"] == "%d.%m.%Y"


def test_inspect_empty_file_is_400(client):
    assert upload(client, "inspect", b"").status_code == 400


# -- preview -----------------------------------------------------------------


def test_preview_validity_counts(client):
    setup_account(client)
    response = upload(client, "preview", BANK_CSV, mapping=full_mapping())
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["counts"] == {"total": 4, "valid": 3, "invalid": 1, "duplicates": 0}
    broken = next(row for row in result["rows"] if not row["valid"])
    assert broken["row_number"] == 5
    assert any("Amount" in error for error in broken["errors"])
    # No writes happened during preview.
    assert client.get("/api/v1/transactions").json()["total"] == 0


def test_preview_resolves_account_and_category(client):
    setup_account(client)
    client.get("/api/v1/categories")  # seeds the defaults
    result = upload(client, "preview", BANK_CSV, mapping=full_mapping()).json()
    first = result["rows"][0]
    assert first["account_id"] is not None
    assert first["account_name"] == "Checking"
    assert first["category_state"] == "existing"  # Housing is seeded
    assert first["duplicate"] is False


def test_preview_maps_unknown_account_to_default(client):
    account = setup_account(client)
    csv_data = b"Date,Description,Amount\n2026-09-01,Store,-10.00\n"
    mapping = {
        "fields": {"date": {"column": 0}, "description": {"column": 1}, "amount": {"column": 2}},
        "options": {"default_account_id": account["id"]},
    }
    result = upload(client, "preview", csv_data, mapping=mapping).json()
    assert result["rows"][0]["account_id"] == account["id"]


def test_preview_flags_rows_without_account(client):
    csv_data = b"Date,Description,Amount\n2026-09-01,Store,-10.00\n"
    mapping = {
        "fields": {"date": {"column": 0}, "description": {"column": 1}, "amount": {"column": 2}}
    }
    result = upload(client, "preview", csv_data, mapping=mapping).json()
    row = result["rows"][0]
    assert row["valid"] is False
    assert any("account" in error.lower() for error in row["errors"])


def test_preview_missing_date_column_is_400(client):
    mapping = {"fields": {"description": {"column": 1}, "amount": {"column": 2}}}
    assert upload(client, "preview", BANK_CSV, mapping=mapping).status_code == 400


def test_preview_unknown_mapping_field_is_400(client):
    mapping = {"fields": {"banana": {"column": 0}}}
    assert upload(client, "preview", BANK_CSV, mapping=mapping).status_code == 400


def test_preview_malformed_mapping_json_is_400(client):
    assert upload(client, "preview", BANK_CSV, mapping="{not json").status_code == 400


# -- commit ------------------------------------------------------------------


def test_commit_creates_transactions(client):
    account = setup_account(client)
    result = upload(client, "commit", BANK_CSV, mapping=full_mapping()).json()
    assert result["counts"]["created"] == 3
    assert result["counts"]["skipped_invalid"] == 1
    assert len(result["batch_id"]) == 32
    assert result["accounts_touched"] == [account["id"]]

    items = client.get("/api/v1/transactions").json()["items"]
    assert len(items) == 3
    rent = next(item for item in items if item["description"] == "Rent payment")
    assert rent["type"] == "expense"
    assert rent["amount"] == 1200
    assert client.get(f"/api/v1/accounts/{account['id']}").json()["current_balance"] == 1896.5


def test_commit_is_idempotent(client):
    setup_account(client)
    first = upload(client, "commit", BANK_CSV, mapping=full_mapping()).json()
    assert first["counts"]["created"] == 3

    second = upload(client, "commit", BANK_CSV, mapping=full_mapping()).json()
    assert second["counts"]["created"] == 0
    assert second["counts"]["skipped_duplicates"] == 3
    assert client.get("/api/v1/transactions").json()["total"] == 3


def test_preview_shows_duplicates_after_import(client):
    setup_account(client)
    upload(client, "commit", BANK_CSV, mapping=full_mapping())
    result = upload(client, "preview", BANK_CSV, mapping=full_mapping()).json()
    assert result["counts"]["duplicates"] == 3
    assert result["counts"]["valid"] == 0


def test_commit_creates_missing_categories(client):
    account = setup_account(client)
    csv_data = b"Date,Description,Amount,Category\n2026-09-01,Stuff,-9.99,Brand New Cat\n"
    mapping = {
        "fields": {"date": {"column": 0}, "description": {"column": 1}, "amount": {"column": 2}, "category": {"column": 3}},
        "options": {"default_account_id": account["id"]},
    }
    result = upload(client, "commit", csv_data, mapping=mapping).json()
    assert result["counts"]["categories_created"] == 1
    categories = client.get("/api/v1/categories").json()
    assert "Brand New Cat" in [row["name"] for row in categories]


def test_commit_eu_debit_credit(client):
    account = setup_account(client)
    mapping = {
        "fields": {
            "date": {"column": 0},
            "description": {"column": 1},
            "debit": {"column": 2},
            "credit": {"column": 3},
        },
        "options": {"filename": "eu.csv", "default_account_id": account["id"]},
    }
    result = upload(client, "commit", SEMICOLON_CSV, filename="eu.csv", mapping=mapping).json()
    assert result["counts"]["created"] == 2
    items = client.get("/api/v1/transactions").json()["items"]
    by_description = {item["description"]: item for item in items}
    assert by_description["Rewe"]["type"] == "expense"
    assert by_description["Rewe"]["amount"] == 12.34
    assert by_description["Gehalt"]["type"] == "income"
    assert by_description["Gehalt"]["amount"] == 1500.5
    assert client.get(f"/api/v1/accounts/{account['id']}").json()["current_balance"] == 1588.16


def test_amount_mode_forces_direction(client):
    account = setup_account(client)
    csv_data = b"Date,Description,Amount\n2026-09-01,Positive entry,50.00\n"
    fields = {"date": {"column": 0}, "description": {"column": 1}, "amount": {"column": 2}}

    upload(
        client,
        "commit",
        csv_data,
        mapping={
            "fields": fields,
            "options": {"amount_mode": "expense", "default_account_id": account["id"]},
        },
    )
    item = client.get("/api/v1/transactions").json()["items"][0]
    assert item["type"] == "expense"
    assert item["amount"] == 50


def test_positive_is_expense_convention(client):
    account = setup_account(client)
    csv_data = b"Date,Description,Amount\n2026-09-01,Withdrawal,50.00\n2026-09-02,Deposit,-20.00\n"
    fields = {"date": {"column": 0}, "description": {"column": 1}, "amount": {"column": 2}}
    result = upload(
        client,
        "commit",
        csv_data,
        mapping={
            "fields": fields,
            "options": {"positive_is": "expense", "default_account_id": account["id"]},
        },
    ).json()
    assert result["counts"]["created"] == 2
    types = {item["description"]: item["type"] for item in client.get("/api/v1/transactions").json()["items"]}
    assert types == {"Withdrawal": "expense", "Deposit": "income"}


def test_default_category_used_when_row_has_none(client):
    account = setup_account(client)
    food = next(
        row for row in client.get("/api/v1/categories").json() if row["name"] == "Food"
    )
    csv_data = b"Date,Description,Amount\n2026-09-01,Lunch,-12.00\n"
    fields = {"date": {"column": 0}, "description": {"column": 1}, "amount": {"column": 2}}
    upload(
        client,
        "commit",
        csv_data,
        mapping={
            "fields": fields,
            "options": {
                "default_account_id": account["id"],
                "default_category_id": food["id"],
            },
        },
    )
    item = client.get("/api/v1/transactions").json()["items"][0]
    assert item["category_id"] == food["id"]


def test_invalid_default_account_is_404(client):
    csv_data = b"Date,Description,Amount\n2026-09-01,X,-1.00\n"
    mapping = {
        "fields": {"date": {"column": 0}, "description": {"column": 1}, "amount": {"column": 2}},
        "options": {"default_account_id": 999},
    }
    assert upload(client, "commit", csv_data, mapping=mapping).status_code == 404


# -- pure domain helpers ------------------------------------------------------


def test_parse_amount_formats():
    from app.domain.csv_import import parse_amount

    assert parse_amount("1.234,56") == 1234.56
    assert parse_amount("1,234.56") == 1234.56
    assert parse_amount("(12.30)") == -12.3
    assert parse_amount("1,234") == 1234
    assert parse_amount("1.50") == 1.5
    assert parse_amount("$1,500.50") == 1500.5
    assert parse_amount("12,34") == 12.34
    assert parse_amount(",1500,50") == 1500.5
    assert parse_amount("") is None
    assert parse_amount("abc") is None


def test_parse_date_formats():
    from app.domain.csv_import import parse_date

    assert parse_date("2026-10-01").isoformat() == "2026-10-01"
    assert parse_date("01.10.2026").isoformat() == "2026-10-01"
    assert parse_date("01/10/2026").isoformat() == "2026-10-01"
    assert parse_date("2026-10-01 09:30").isoformat() == "2026-10-01"
    assert parse_date("not a date") is None
