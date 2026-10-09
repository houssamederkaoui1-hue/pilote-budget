"""Phase 7 tests: settings, on-boarding, backup/restore, Quick Add, assistant.

Each test uses the shared fresh SQLite ``client`` fixture so state never leaks
between scenarios.
"""

from __future__ import annotations

from datetime import date, timedelta

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _create_account(client, name, **payload) -> dict:
    body = {
        "name": name,
        "type": "checking",
        "opening_balance": 0,
        **payload,
    }
    response = client.post("/api/v1/accounts", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _create_category(client, name, type_) -> dict:
    response = client.post("/api/v1/categories", json={"name": name, "type": type_})
    assert response.status_code == 201, response.text
    return response.json()


def _create_transaction(client, *, account_id, type_="expense", amount=10.0,
                        description="Coffee", on=None, category_id=None) -> dict:
    body = {
        "type": type_,
        "amount": amount,
        "account_id": account_id,
        "date": (on or date.today()).isoformat(),
        "description": description,
    }
    if category_id is not None:
        body["category_id"] = category_id
    response = client.post("/api/v1/transactions", json=body)
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------
# settings
# --------------------------------------------------------------------------


def test_settings_defaults(client) -> None:
    body = client.get("/api/v1/settings").json()
    assert body["currency"] == "EUR"
    assert body["month_start_day"] == 1
    assert body["minimum_reserve"] == 0.0
    assert body["default_account_id"] is None
    assert body["dashboard"]["period"] == "current"
    assert all(view is True for view in body["dashboard"]["sections"].values())
    assert body["dashboard"]["order"]


def test_settings_partial_update_round_trip(client) -> None:
    checking = _create_account(client, "Checking")
    expenses = _create_category(client, "Food", "expense")

    response = client.put(
        "/api/v1/settings",
        json={
            "currency": "usd",
            "month_start_day": 15,
            "minimum_reserve": 250.5,
            "default_account_id": checking["id"],
            "default_expense_category_id": expenses["id"],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["currency"] == "USD"
    assert body["month_start_day"] == 15
    assert body["minimum_reserve"] == 250.5
    assert body["default_account_id"] == checking["id"]
    assert body["default_expense_category_id"] == expenses["id"]

    # A partial update must not clobber earlier values.
    again = client.put("/api/v1/settings", json={"minimum_reserve": 0}).json()
    assert again["minimum_reserve"] == 0.0
    assert again["currency"] == "USD"
    assert again["default_account_id"] == checking["id"]


def test_settings_validation_errors(client) -> None:
    assert client.put("/api/v1/settings", json={"currency": "XXX"}).status_code == 400
    assert client.put("/api/v1/settings", json={"minimum_reserve": -1}).status_code == 400
    assert (
        client.put("/api/v1/settings", json={"month_start_day": 0}).status_code in (400, 422)
    )

    archived = _create_account(client, "Closed", active=False)
    assert (
        client.put("/api/v1/settings", json={"default_account_id": archived["id"]}).status_code
        == 400
    )

    savings = _create_category(client, "Piggy bank", "income")
    assert (
        client.put(
            "/api/v1/settings", json={"default_expense_category_id": savings["id"]}
        ).status_code
        == 400
    )

    assert (
        client.put("/api/v1/settings", json={"dashboard": {"period": "never"}}).status_code
        == 400
    )
    assert (
        client.put(
            "/api/v1/settings",
            json={"dashboard": {"order": ["stats", "stats"]}},
        ).status_code
        == 400
    )


def test_settings_dashboard_personalization_round_trip(client) -> None:
    response = client.put(
        "/api/v1/settings",
        json={
            "dashboard": {
                "period": "last_three",
                "sections": {"stats": True, "goals": False, "cash_flow": False},
                "order": ["stats", "forecast", "goals"],
            }
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["dashboard"]["period"] == "last_three"
    assert body["dashboard"]["sections"]["goals"] is False
    assert body["dashboard"]["sections"]["cash_flow"] is False
    assert body["dashboard"]["sections"]["stats"] is True
    # Order is completed with the missing (still visible) sections.
    order = body["dashboard"]["order"]
    assert order[0] == "stats"
    assert order.index("forecast") < order.index("insights")


def test_analytics_honours_dashboard_period(client) -> None:
    _create_account(client, "Checking", opening_balance=1000)
    default = client.get("/api/v1/analytics").json()
    assert len(default["history"]) == 7

    short = client.get("/api/v1/analytics", params={"months": 1}).json()
    assert len(short["history"]) == 1

    three = client.get("/api/v1/analytics", params={"months": 3}).json()
    assert len(three["history"]) == 3


# --------------------------------------------------------------------------
# on-boarding
# --------------------------------------------------------------------------


def test_onboarding_tracks_real_state(client) -> None:
    state = client.get("/api/v1/settings/onboarding").json()
    assert state["completed"] is False
    assert state["skipped"] is False
    by_id = {step["id"]: step for step in state["steps"]}
    assert by_id["account"]["complete"] is False
    assert by_id["budget"]["optional"] is True

    _create_account(client, "Checking")
    _create_category(client, "Food", "expense")

    state = client.get("/api/v1/settings/onboarding").json()
    assert state["completed"] is True
    by_id = {step["id"]: step for step in state["steps"]}
    assert by_id["account"]["complete"] is True
    assert by_id["categories"]["complete"] is True


def test_onboarding_can_be_skipped(client) -> None:
    state = client.put("/api/v1/settings/onboarding", json={"skipped": True}).json()
    assert state["skipped"] is True
    state = client.get("/api/v1/settings/onboarding").json()
    assert state["skipped"] is True


# --------------------------------------------------------------------------
# Quick Add + suggestions
# --------------------------------------------------------------------------


def test_quick_capture_uses_defaults_and_suggests_category(client) -> None:
    checking = _create_account(client, "Checking")
    food = _create_category(client, "Dining out", "expense")
    _create_transaction(client, account_id=checking["id"], description="McDonald'S lunch",
                        amount=8.5, category_id=food["id"])

    client.put(
        "/api/v1/settings",
        json={"default_account_id": checking["id"], "default_expense_category_id": food["id"]},
    )

    result = client.post(
        "/api/v1/quick/capture",
        json={
            "type": "expense",
            "amount": 8.5,
            "description": "McDonald's lunch",
            "date": date.today().isoformat(),
        },
    ).json()
    assert result["account_id"] == checking["id"]
    assert result["category_id"] == food["id"]
    assert result["duplicates"], "expected a near-duplicate match"
    assert result["duplicates"][0]["same_day"] is True
    top = result["categories"][0]
    assert top["category_id"] == food["id"]
    assert top["confidence"] == "exact"


def test_quick_create_applies_defaults(client) -> None:
    checking = _create_account(client, "Checking")
    food = _create_category(client, "Food", "expense")
    client.put(
        "/api/v1/settings",
        json={"default_account_id": checking["id"], "default_expense_category_id": food["id"]},
    )

    result = client.post(
        "/api/v1/quick/transactions",
        json={
            "type": "expense",
            "amount": 12.0,
            "description": "Groceries",
            "date": date.today().isoformat(),
        },
    ).json()
    assert result["transaction"]["account_id"] == checking["id"]
    assert result["transaction"]["category_id"] == food["id"]

    warned = client.post(
        "/api/v1/quick/transactions",
        json={
            "type": "expense",
            "amount": 12.0,
            "description": "Groceries",
            "date": date.today().isoformat(),
        },
    ).json()
    assert warned["duplicates"], "re-adding the same entry should be flagged"


def test_quick_create_can_reject_duplicates(client) -> None:
    checking = _create_account(client, "Checking")
    food = _create_category(client, "Food", "expense")
    client.put(
        "/api/v1/settings",
        json={"default_account_id": checking["id"], "default_expense_category_id": food["id"]},
    )
    _create_transaction(client, account_id=checking["id"], description="Groceries",
                        amount=12.0, category_id=food["id"])

    status = client.post(
        "/api/v1/quick/transactions",
        json={
            "type": "expense",
            "amount": 12.0,
            "description": "Groceries",
            "date": date.today().isoformat(),
            "reject_duplicate": True,
        },
    )
    assert status.status_code == 409


def test_quick_create_without_any_account_errors(client) -> None:
    response = client.post(
        "/api/v1/quick/transactions",
        json={"type": "expense", "amount": 5, "description": "x", "date": date.today().isoformat()},
    )
    assert response.status_code == 400


# --------------------------------------------------------------------------
# backup / restore
# --------------------------------------------------------------------------


def _seed_kitchen_sink(client) -> dict:
    assert client.get("/api/v1/profile").status_code == 200  # ensures profile row
    checking = _create_account(client, "Checking", opening_balance=500)
    savings = _create_account(client, "Savings", opening_balance=1000)
    food = _create_category(client, "Food", "expense")
    salary = _create_category(client, "Salary", "income")
    _create_transaction(client, account_id=checking["id"], description="Groceries",
                        amount=45.0, category_id=food["id"])
    client.post(
        "/api/v1/goals",
        json={"name": "Vacation", "target_amount": 2000, "current_amount": 400},
    )
    due = date.today() + timedelta(days=5)
    client.post(
        "/api/v1/recurring",
        json={"account_id": checking["id"], "type": "expense", "amount": 120,
              "frequency": "monthly", "next_occurrence": due.isoformat(),
              "description": "Internet", "category_id": food["id"]},
    )
    return {
        "accounts": (checking["id"], savings["id"]),
        "categories": (food["id"], salary["id"]),
    }


def test_backup_export_validate_and_preview(client) -> None:
    _seed_kitchen_sink(client)
    exported = client.get("/api/v1/backup/export").json()
    assert exported["format"] == "pilote-budget-backup"
    assert exported["version"] == 1
    counts = {row["table"]: row["rows"] for row in exported["counts"]}
    assert counts["accounts"] == 2
    assert counts["transactions"] == 1
    assert counts["categories"] == 2

    validated = client.post("/api/v1/backup/validate", json=exported).json()
    assert validated["valid"] is True


def test_backup_restore_round_trip_replaces_data(client) -> None:
    ids = _seed_kitchen_sink(client)
    exported = client.get("/api/v1/backup/export").json()

    # Add a marker entry after the export; restore must remove it.
    _create_transaction(client, account_id=ids["accounts"][0], description="Marker",
                        amount=1.0)
    assert client.get("/api/v1/transactions").json()["total"] == 2

    preview = client.post("/api/v1/backup/validate", json=exported).json()
    assert preview["valid"] is True

    restored = client.post(
        "/api/v1/backup/restore", json={"payload": exported, "confirmed": True}
    ).json()
    assert restored["valid"] is True
    counts = {row["table"]: row["rows"] for row in restored["counts"]}
    assert counts["transactions"] == 1
    assert counts["accounts"] == 2

    transactions = client.get("/api/v1/transactions").json()["items"]
    assert len(transactions) == 1
    assert transactions[0]["description"] == "Groceries"
    goals = client.get("/api/v1/goals").json()
    assert any(g["name"] == "Vacation" for g in goals)
    profile = client.get("/api/v1/profile").json()
    assert profile["id"] == 1


def test_backup_restore_requires_confirmation(client) -> None:
    ids = _seed_kitchen_sink(client)
    exported = client.get("/api/v1/backup/export").json()
    response = client.post("/api/v1/backup/restore", json={"payload": exported, "confirmed": False})
    assert response.status_code == 400


def test_backup_validation_rejects_bad_payloads(client) -> None:
    assert client.post("/api/v1/backup/validate", json={"foo": 1}).status_code == 400
    assert client.post("/api/v1/backup/validate", json={"format": "x", "version": 1}).status_code == 400
    future = client.get("/api/v1/backup/export").json()
    future["version"] = 99
    assert client.post("/api/v1/backup/validate", json=future).status_code == 400

    broken = client.get("/api/v1/backup/export").json()
    broken["data"]["profiles"] = []
    assert client.post("/api/v1/backup/validate", json=broken).status_code == 400

    dangling = client.get("/api/v1/backup/export").json()
    dangling["data"]["transactions"].append(
        {"id": 9999, "account_id": 424242, "category_id": None, "type": "expense",
         "amount": 5, "date": "2026-10-01", "description": "ghost", "notes": None,
         "status": "cleared", "created_at": None, "updated_at": None}
    )
    assert client.post("/api/v1/backup/validate", json=dangling).status_code == 400


# --------------------------------------------------------------------------
# assistant additions
# --------------------------------------------------------------------------


def test_assistant_answers_new_intents(client) -> None:
    checking = _create_account(client, "Checking", opening_balance=5000)
    salary = _create_category(client, "Salary", "income")
    food = _create_category(client, "Food", "expense")
    _create_transaction(client, account_id=checking["id"], type_="income",
                        description="Paycheck", amount=3000, category_id=salary["id"])
    _create_transaction(client, account_id=checking["id"], description="Rent",
                        amount=1200)
    client.post(
        "/api/v1/goals",
        json={"name": "Emergency fund", "target_amount": 6000, "current_amount": 1500},
    )
    due = date.today() + timedelta(days=3)
    client.post(
        "/api/v1/recurring",
        json={"account_id": checking["id"], "type": "expense", "amount": 89,
              "frequency": "monthly", "next_occurrence": due.isoformat(),
              "description": "Streaming"},
    )

    checks = {
        "upcoming": ("plan", True),
        "insights": ("ledger", True),
        "net_worth_contributors": ("ledger", True),
        "goals_progress": ("plan", True),
    }
    for intent, (source, recognized) in checks.items():
        response = client.post("/api/v1/assistant/ask", json={"question": intent, "intent": intent})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["recognized"] is recognized, (intent, body)
        assert body["answer"], intent
        assert body["source"] == source, intent

    upcoming = client.post(
        "/api/v1/assistant/ask", json={"question": "What bills are coming up?", "intent": "upcoming"}
    ).json()
    assert "Streaming" in upcoming["answer"]


def test_assistant_match_intent_routes_new_questions(client) -> None:
    pairs = {
        "What bills are coming up?": "upcoming",
        "What should I pay attention to?": "insights",
        "How are my goals progressing?": "goals_progress",
        "What is driving my net worth?": "net_worth_contributors",
    }
    for question, expected in pairs.items():
        body = client.post("/api/v1/assistant/ask", json={"question": question}).json()
        assert body["intent"] == expected, body


def test_assistant_upcoming_works_without_transactions(client) -> None:
    checking = _create_account(client, "Checking")
    due = date.today() + timedelta(days=4)
    client.post(
        "/api/v1/recurring",
        json={"account_id": checking["id"], "type": "expense", "amount": 12,
              "frequency": "monthly", "next_occurrence": due.isoformat(),
              "description": "Netflix"},
    )
    body = client.post(
        "/api/v1/assistant/ask", json={"question": "What bills are coming up?", "intent": "upcoming"}
    ).json()
    assert body["recognized"] is True
    assert "Netflix" in body["answer"]