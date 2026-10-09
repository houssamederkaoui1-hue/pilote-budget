"""Database initialization and schema tests."""

from __future__ import annotations

from datetime import date

from sqlalchemy import inspect

from app.db.schema import create_all, ensure_schema, existing_tables
from app.db.session import get_engine
from app.models import Account, Category, Debt, Goal, RecurringTransaction, Transaction

EXPECTED_TABLES = {
    "accounts",
    "budgets",
    "categories",
    "debts",
    "goals",
    "profiles",
    "recurring_transactions",
    "transactions",
    "transfers",
}


def test_migrations_create_every_table(settings) -> None:
    ensure_schema(settings)
    tables = set(existing_tables())
    assert EXPECTED_TABLES <= tables
    assert "alembic_version" in tables


def test_schema_creation_is_idempotent(settings) -> None:
    ensure_schema(settings)
    first = existing_tables()
    ensure_schema(settings)
    assert existing_tables() == first


def test_create_all_matches_migrated_schema(settings) -> None:
    ensure_schema(settings)
    migrated = set(existing_tables())

    # A second, non-migrated database created from metadata must match.
    import os
    import tempfile

    from app.config import get_settings
    from app.db.session import reset_engine

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["PILOTE_DATABASE_URL"] = f"sqlite:///{tmp}/fresh.db"
        get_settings.cache_clear()
        reset_engine()
        try:
            create_all()
            from_metadata = set(existing_tables())
        finally:
            reset_engine()
            get_settings.cache_clear()

    assert from_metadata == migrated - {"alembic_version"}


def test_roundtrip_write_and_read(session) -> None:
    session.add(Account(name="Main checking", opening_balance=100.0, current_balance=100.0))
    session.add(Category(name="Groceries", type="expense"))
    session.flush()

    account = session.query(Account).one()
    category = session.query(Category).one()
    session.add(
        Transaction(
            account_id=account.id,
            category_id=category.id,
            type="expense",
            amount=42.5,
            date=date(2026, 10, 1),
            description="Weekly shopping",
        )
    )
    session.commit()

    transaction = session.query(Transaction).one()
    assert transaction.amount == 42.5
    assert transaction.status == "cleared"
    assert transaction.account.name == "Main checking"
    assert transaction.created_at is not None


def test_account_name_is_unique(session) -> None:
    from sqlalchemy.exc import IntegrityError

    session.add(Account(name="Duplicate", opening_balance=0.0, current_balance=0.0))
    session.flush()
    session.add(Account(name="Duplicate", opening_balance=0.0, current_balance=0.0))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
    else:  # pragma: no cover
        raise AssertionError("expected unique constraint violation")


def test_money_and_enums_survive_roundtrip(session) -> None:
    session.add(Account(name="Savings", type="savings", opening_balance=1500.25))
    session.flush()
    session.add(
        Goal(name="Emergency fund", target_amount=10000.0, current_amount=2500.0)
    )
    session.add(
        RecurringTransaction(
            account_id=session.query(Account).one().id,
            type="income",
            amount=3000.0,
            frequency="monthly",
            next_occurrence=date(2026, 11, 1),
        )
    )
    session.add(Debt(name="Card", original_amount=5000.0, remaining_amount=3200.0))
    session.flush()
    session.commit()

    assert session.query(Goal).one().current_amount == 2500.0
    assert session.query(RecurringTransaction).one().frequency == "monthly"
    assert session.query(Debt).one().remaining_amount == 3200.0
    assert session.query(Account).one().type == "savings"


def test_foreign_keys_are_enforced(settings, session) -> None:
    from sqlalchemy.exc import IntegrityError

    session.add(
        Transaction(
            account_id=999999,
            type="expense",
            amount=10.0,
            date=date(2026, 10, 1),
        )
    )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
    else:  # pragma: no cover
        raise AssertionError("expected foreign key violation")


def test_inspector_reports_expected_columns() -> None:
    from app.db.schema import ensure_schema
    from app.config import get_settings

    ensure_schema(get_settings())
    columns = {c["name"] for c in inspect(get_engine()).get_columns("transactions")}
    assert {
        "id",
        "account_id",
        "category_id",
        "type",
        "amount",
        "date",
        "description",
        "notes",
        "status",
        "import_batch_id",
        "external_id",
        "import_metadata",
        "created_at",
        "updated_at",
    } <= columns
