"""Recurring templates: projection, record/advance, deactivation rules.

Three behaviours are pinned down here:
- upcoming is a pure projection (never writes);
- templates never self-post: only record/advance move the schedule;
- an overdue occurrence is reported once and not extrapolated.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.domain.errors import ValidationError
from app.domain.schedules import months_shift
from app.services.recurring_service import RecurringService


def create_account(client, name, **payload):
    return client.post("/api/v1/accounts", json={"name": name, **payload}).json()


def create_expense_category(client, name):
    response = client.post("/api/v1/categories", json={"name": name, "type": "expense"})
    assert response.status_code == 201, response.text
    return response.json()


def create_income_category(client, name):
    response = client.post("/api/v1/categories", json={"name": name, "type": "income"})
    assert response.status_code == 201, response.text
    return response.json()


def make_template(client, **payload):
    payload.setdefault("account_id", 1)
    response = client.post("/api/v1/recurring", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def upcoming(client, days=30):
    response = client.get("/api/v1/recurring/upcoming", params={"days": days})
    assert response.status_code == 200, response.text
    return response.json()


def balance(client, account_id):
    return client.get(f"/api/v1/accounts/{account_id}").json()["current_balance"]


def test_monthly_record_posts_and_steps(client):
    account = create_account(client, "Checking")
    category = create_expense_category(client, "Subscriptions")
    today = date.today()
    tpl = make_template(
        client,
        account_id=account["id"],
        type="expense",
        amount=40,
        frequency="monthly",
        next_occurrence=(today + timedelta(days=5)).isoformat(),
        category_id=category["id"],
    )

    response = client.post(f"/api/v1/recurring/{tpl['id']}/record")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["date"] == (today + timedelta(days=5)).isoformat()
    assert result["next_occurrence"] == months_shift(today + timedelta(days=5), 1).isoformat()
    assert result["deactivated"] is False
    assert balance(client, account["id"]) == -40.0

    occ = [o for o in upcoming(client, days=40)["occurrences"] if o["recurring_id"] == tpl["id"]]
    assert len(occ) == 1
    assert occ[0]["due_date"] == months_shift(today + timedelta(days=5), 1).isoformat()
    assert occ[0]["overdue"] is False


def test_record_income_increases_balance(client):
    account = create_account(client, "Checking")
    category = create_income_category(client, "Salary")
    today = date.today()
    tpl = make_template(
        client,
        account_id=account["id"],
        type="income",
        amount=2500,
        frequency="monthly",
        next_occurrence=today.isoformat(),
        category_id=category["id"],
    )
    response = client.post(f"/api/v1/recurring/{tpl['id']}/record")
    assert response.status_code == 200
    assert balance(client, account["id"]) == 2500.0


def test_weekly_projection_multiple_occurrences(client):
    account = create_account(client, "Checking")
    today = date.today()
    tpl = make_template(
        client,
        account_id=account["id"],
        type="expense",
        amount=20,
        frequency="weekly",
        next_occurrence=(today + timedelta(days=3)).isoformat(),
    )
    occ = [
        o["due_date"]
        for o in upcoming(client)["occurrences"]
        if o["recurring_id"] == tpl["id"]
    ]
    expected = [
        (today + timedelta(days=3)).isoformat(),
        (today + timedelta(days=10)).isoformat(),
        (today + timedelta(days=17)).isoformat(),
        (today + timedelta(days=24)).isoformat(),
    ]
    assert occ == expected


def test_monthly_clamps_to_month_end(session, client):
    account = create_account(client, "Checking")
    service = RecurringService(session)
    service.create(
        account_id=account["id"],
        type="expense",
        amount=10,
        frequency="monthly",
        next_occurrence=date(2026, 1, 31),
    )
    session.flush()

    occ = service.upcoming(date(2026, 1, 1), days=90)["occurrences"]
    due = [o["due_date"] for o in occ]
    assert date(2026, 1, 31) in due
    assert date(2026, 2, 28) in due
    assert date(2026, 3, 28) in due  # anchors to the clamped 28th
    assert date(2026, 3, 31) not in due

    template = service.list()[0]
    recorded = service.record(template["id"])
    assert recorded["next_occurrence"] == date(2026, 2, 28)


def test_advance_skips_without_posting(client):
    account = create_account(client, "Checking")
    today = date.today()
    tpl = make_template(
        client,
        account_id=account["id"],
        type="expense",
        amount=50,
        frequency="monthly",
        next_occurrence=(today + timedelta(days=7)).isoformat(),
    )
    response = client.post(f"/api/v1/recurring/{tpl['id']}/advance")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["next_occurrence"] == months_shift(today + timedelta(days=7), 1).isoformat()
    assert result["deactivated"] is False
    assert balance(client, account["id"]) == 0.0


def test_overdue_is_reported_once(client):
    account = create_account(client, "Checking")
    today = date.today()
    tpl = make_template(
        client,
        account_id=account["id"],
        type="expense",
        amount=30,
        frequency="weekly",
        next_occurrence=(today - timedelta(days=3)).isoformat(),
    )
    occ = [
        o for o in upcoming(client)["occurrences"] if o["recurring_id"] == tpl["id"]
    ]
    assert len(occ) == 1
    assert occ[0]["due_date"] == (today - timedelta(days=3)).isoformat()
    assert occ[0]["overdue"] is True

    response = client.post(f"/api/v1/recurring/{tpl['id']}/record")
    assert response.status_code == 200
    assert response.json()["date"] == (today - timedelta(days=3)).isoformat()
    assert balance(client, account["id"]) == -30.0


def test_end_date_deactivates_after_record(client):
    account = create_account(client, "Checking")
    today = date.today()
    tpl = make_template(
        client,
        account_id=account["id"],
        type="expense",
        amount=10,
        frequency="monthly",
        next_occurrence=(today + timedelta(days=1)).isoformat(),
        end_date=(today + timedelta(days=2)).isoformat(),
    )
    response = client.post(f"/api/v1/recurring/{tpl['id']}/record")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["deactivated"] is True
    assert result["template"]["active"] is False
    assert balance(client, account["id"]) == -10.0

    listed = client.get("/api/v1/recurring").json()
    assert next(item for item in listed if item["id"] == tpl["id"])["active"] is False


def test_inactive_templates_excluded_from_upcoming(client):
    account = create_account(client, "Checking")
    today = date.today()
    tpl = make_template(
        client,
        account_id=account["id"],
        type="expense",
        amount=10,
        frequency="daily",
        next_occurrence=(today + timedelta(days=1)).isoformat(),
        active=False,
    )
    occ = [
        o for o in upcoming(client)["occurrences"] if o["recurring_id"] == tpl["id"]
    ]
    assert occ == []
    assert client.post(f"/api/v1/recurring/{tpl['id']}/record").status_code == 400


def test_transfer_and_custom_frequencies_rejected(client):
    account = create_account(client, "Checking")
    response = client.post(
        "/api/v1/recurring",
        json={
            "account_id": account["id"],
            "type": "transfer",
            "amount": 10,
            "frequency": "monthly",
        },
    )
    assert response.status_code == 400
    assert "Scheduled transfers" in response.json()["detail"]

    response = client.post(
        "/api/v1/recurring",
        json={
            "account_id": account["id"],
            "type": "expense",
            "amount": 10,
            "frequency": "custom",
        },
    )
    assert response.status_code == 400
    assert "Custom frequencies" in response.json()["detail"]


def test_category_type_mismatch_rejected(client):
    account = create_account(client, "Checking")
    category = create_income_category(client, "Investment Income")
    response = client.post(
        "/api/v1/recurring",
        json={
            "account_id": account["id"],
            "type": "expense",
            "amount": 10,
            "frequency": "monthly",
            "category_id": category["id"],
        },
    )
    assert response.status_code == 400


def test_end_date_before_next_occurrence_rejected(client):
    account = create_account(client, "Checking")
    response = client.post(
        "/api/v1/recurring",
        json={
            "account_id": account["id"],
            "type": "expense",
            "amount": 10,
            "frequency": "monthly",
            "next_occurrence": "2026-10-20",
            "end_date": "2026-10-10",
        },
    )
    assert response.status_code == 400


def test_delete(client):
    account = create_account(client, "Checking")
    tpl = make_template(
        client, account_id=account["id"], type="expense", amount=5, frequency="weekly"
    )
    assert client.delete(f"/api/v1/recurring/{tpl['id']}").status_code == 200
    assert client.get("/api/v1/recurring").json() == []


def test_upcoming_stops_at_end_date(session, client):
    account = create_account(client, "Checking")
    service = RecurringService(session)
    service.create(
        account_id=account["id"],
        type="expense",
        amount=10,
        frequency="monthly",
        next_occurrence=date(2026, 10, 20),
        end_date=date(2026, 11, 15),
    )
    session.flush()

    occ = service.upcoming(date(2026, 10, 8), days=180)["occurrences"]
    due = [o["due_date"] for o in occ]
    # Nov 20 and Dec 20 fall after end_date and must not be projected.
    assert due == [date(2026, 10, 20)]


def test_record_rejects_outside_current_due_window(session, client):
    account = create_account(client, "Checking")
    service = RecurringService(session)
    service.create(
        account_id=account["id"],
        type="expense",
        amount=10,
        frequency="monthly",
        next_occurrence=date(2026, 9, 20),  # overdue relative to today
    )
    session.flush()
    template = service.list()[0]

    # The due occurrence itself is accepted.
    first = service.record(template["id"])
    assert first["date"] == date(2026, 9, 20)

    # Encoding the same due again (now one cycle late) must fail: the schedule
    # has already advanced, otherwise two ledger rows would appear for it.
    with pytest.raises(ValidationError):
        service.record(template["id"], at_date=date(2026, 9, 20))

    # Far-future and far-past dates are outside the current window too.
    with pytest.raises(ValidationError):
        service.record(template["id"], at_date=date(2026, 12, 1))
    with pytest.raises(ValidationError):
        service.record(template["id"], at_date=date(2026, 8, 1))