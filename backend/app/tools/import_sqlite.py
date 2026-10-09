"""Operator-initiated SQLite -> PostgreSQL import.

This tool copies the *entire* application data layer (profiles, categories,
accounts, budget allocations, goals, debts, budgets, transactions, transfers,
recurring transactions) from the local SQLite file into a Postgres database,
preserving every primary key and all foreign-key relationships, then re-arms
the Postgres identity sequences.

Safety rules:
- **It never runs automatically.** The app's startup never imports anything.
- It refuses to overwrite a Postgres database that already contains data
  (use ``--force`` deliberately to change that).
- It never writes to the SQLite source.
- ``--yes`` (or an interactive confirmation) is required to actually copy.

Examples::

    uv run python -m app.tools.import_sqlite --sqlite data/pilote_budget.db \
        --target "$DATABASE_URL" --check
    uv run python -m app.tools.import_sqlite --sqlite data/pilote_budget.db \
        --target "$DATABASE_URL" --yes

``--check`` connects to the target and reports reachability + whether it is
empty, without changing anything.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import create_engine, insert, select, text
from sqlalchemy.engine import Engine

from app.db.base import Base
from app.domain.backup import TABLE_ORDER

REQUIRED_TABLES = set(TABLE_ORDER)


@dataclass
class ImportResult:
    table_counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.table_counts.values())


def _normalize(url: str) -> str:
    """Add the psycopg driver to bare ``postgres://``/``postgresql://`` URLs."""
    url = url.strip()
    match = re.match(r"^(postgres|postgresql)://", url)
    if match:
        return "postgresql+psycopg" + url[match.end() - 3 :]
    return url


def _masked(url: str) -> str:
    """URL with any password redacted for console output."""
    return re.sub(r"//([^/@:]+):([^@/]+)@", r"//\1:***@", url)


def _order_by_dependency(rows: list[dict], parent_key: str) -> list[dict]:
    """Stable parent-before-child ordering (categories self-referencing)."""
    if not rows:
        return []
    by_id: dict = {row["id"]: row for row in rows}
    depth: dict = {}

    def depth_of(row: dict, seen: set) -> int:
        pid = row.get(parent_key)
        if pid is None or pid == row.get("id"):
            return 0
        if pid in depth:
            return depth[pid] + 1
        parent = by_id.get(pid)
        if parent is None or parent["id"] in seen:
            return 0
        parent_depth = depth_of(parent, seen | {parent["id"]})
        depth[parent["id"]] = parent_depth
        return parent_depth + 1

    for row in rows:
        depth[row["id"]] = depth_of(row, {row["id"]})
    return sorted(rows, key=lambda row: depth.get(row["id"], 0))


def _fetch_row_maps(engine: Engine, table_name: str) -> list[dict]:
    table = Base.metadata.tables[table_name]
    with engine.connect() as connection:
        stmt = select(table)
        if "id" in table.c:
            stmt = stmt.order_by(table.c.id)
        rows = connection.execute(stmt).all()
    return [dict(row._mapping) for row in rows]


def _target_empty(engine: Engine) -> tuple[bool, list[str]]:
    non_empty: list[str] = []
    with engine.connect() as connection:
        for table_name in TABLE_ORDER:
            count = connection.execute(
                text(f"SELECT COUNT(*) FROM {table_name}")
            ).scalar()
            if int(count or 0) > 0:
                non_empty.append(table_name)
    return not non_empty, non_empty


def _fix_postgres_sequences(connection, table_name: str) -> None:
    """Re-arm the identity sequence so new ids continue after the import."""
    sequence = connection.execute(
        text("SELECT pg_get_serial_sequence(:table_name, 'id')"),
        {"table_name": table_name},
    ).scalar()
    if not sequence:
        return
    max_id = connection.execute(
        text(f"SELECT COALESCE(MAX(id), 0) FROM {table_name}")
    ).scalar()
    if int(max_id or 0) > 0:
        connection.execute(
            text("SELECT setval(:sequence, :value)"),
            {"sequence": sequence, "value": int(max_id or 0)},
        )


def import_sqlite(source_url: str, target_url: str, *, force: bool = False) -> ImportResult:
    """Copy every table from ``source_url`` into ``target_url``.

    ``source_url`` must be SQLite; ``target_url`` is typically Postgres (any
    SQLAlchemy URL works, but sequence re-arming only happens for Postgres,
    which is the production target). The target schema is created from the
    models first so the correct column types exist. The CLI enforces that the
    target is a Postgres URL; the core function only enforces the hard rules
    (source is SQLite, databases differ).
    """
    source = _normalize(source_url)
    target = _normalize(target_url)
    if source == target:
        raise SystemExit("Source and target must be different databases.")
    if not source.startswith("sqlite"):
        raise SystemExit("Source must be a SQLite database URL or file path.")

    from app import models  # noqa: F401  (registers models on Base.metadata)

    source_engine = create_engine(source)
    target_engine = create_engine(target, pool_pre_ping=True)

    with source_engine.connect() as connection:
        tables = set(connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).scalars())
    missing = sorted(REQUIRED_TABLES - tables)
    if missing:
        raise SystemExit(
            "Source SQLite database is missing tables: " + ", ".join(missing)
        )

    Base.metadata.create_all(target_engine)

    if not force:
        empty, non_empty = _target_empty(target_engine)
        if not empty:
            raise SystemExit(
                "Target database already contains data in: "
                + ", ".join(non_empty)
                + ". Refusing to overwrite. Use --force to import anyway."
            )

    result = ImportResult()
    with target_engine.begin() as connection:
        for table_name in TABLE_ORDER:
            rows = _fetch_row_maps(source_engine, table_name)
            if table_name == "categories" and rows:
                rows = _order_by_dependency(rows, "parent_id")
            if rows:
                connection.execute(insert(Base.metadata.tables[table_name]), list(rows))
            result.table_counts[table_name] = len(rows)
            if target.startswith("postgresql"):
                _fix_postgres_sequences(connection, table_name)

    source_engine.dispose()
    target_engine.dispose()
    return result


def check_target(target_url: str) -> int:
    """Validate reachability + emptiness of the target without changing it."""
    target = _normalize(target_url)
    try:
        target_engine = create_engine(target, pool_pre_ping=True)
        with target_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as error:  # pragmatic: report the failure and exit nonzero
        print(f"FAIL  cannot reach target {_masked(target)}: {error}")
        return 1

    Base.metadata.create_all(target_engine)
    empty, non_empty = _target_empty(target_engine)
    if empty:
        target_engine.dispose()
        print("OK    target reachable and empty (ready for import).")
        return 0
    counts: dict[str, int] = {}
    with target_engine.connect() as connection:
        for table_name in non_empty:
            counts[table_name] = int(
                connection.execute(
                    text(f"SELECT COUNT(*) FROM {table_name}")
                ).scalar()
            )
    target_engine.dispose()
    total = sum(counts.values())
    print(
        f"WARN  target reachable but NOT empty "
        f"({total} rows already present). Use --force to overwrite."
    )
    return 2


def _cli_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.tools.import_sqlite",
        description="Import a local SQLite database into Postgres. Operator-only.",
    )
    parser.add_argument("--sqlite", required=True, help="SQLite file path or URL.")
    parser.add_argument("--target", required=True, help="Postgres connection URL.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only verify the target is reachable + empty; make no changes.",
    )
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt.")
    parser.add_argument("--force", action="store_true", help="Allow overwriting a non-empty target.")
    args = parser.parse_args(argv)

    sqlite_arg = args.sqlite
    if not sqlite_arg.startswith(("sqlite:", "sqlite:///")):
        path = Path(sqlite_arg).expanduser().resolve()
        sqlite_arg = f"sqlite:///{path}"

    target = _normalize(args.target)
    if not target.startswith("postgresql"):
        parser.error("Target must be a PostgreSQL URL.")

    if args.check:
        return check_target(args.target)

    print(f"Source: {_masked(sqlite_arg)}")
    print(f"Target: {_masked(target)}")
    if not args.yes and not args.force:
        answer = input("This will copy ALL data into the target. Continue? [y/N] ")
        if answer.strip().lower() not in {"y", "yes"}:
            print("Aborted; nothing was changed.")
            return 1

    result = import_sqlite(args.sqlite, args.target, force=args.force)
    print("Imported rows:")
    total = 0
    for table_name in TABLE_ORDER:
        count = result.table_counts.get(table_name, 0)
        total += count
        print(f"  {table_name:<22} {count}")
    print(f"Total: {total} rows. Sequences re-armed (Postgres).")
    return 0


if __name__ == "__main__":
    sys.exit(_cli_main())