"""Backup envelope format: pure validation only (no SQLAlchemy).

A backup payload is a JSON document with a stable envelope:

    {
      "format": "pilote-budget-backup",
      "version": 1,
      "exported_at": "ISO-8601",
      "data": {
        "<table>": [ {row...}, ... ],   # ordered by dependency
        ...
      }
    }

Version bumps are incrementing; ``validate_envelope`` rejects unknown formats
and unsupported future versions so a restore can never silently corrupt data.
"""

from __future__ import annotations

from app.domain.errors import ValidationError

FORMAT = "pilote-budget-backup"
VERSION = 1

# Restore order (parents before children). The service mirrors this for deletes
# (children first) and inserts (parents first).
TABLE_ORDER: tuple[str, ...] = (
    "profiles",
    "categories",       # self-referencing parent_id -> nested sort at restore
    "accounts",
    "budget_allocations",
    "goals",
    "debts",
    "budgets",
    "transactions",
    "transfers",
    "recurring_transactions",
)

REQUIRED_TABLES = frozenset(TABLE_ORDER)


def validate_envelope(payload: dict) -> None:
    """Raise ``ValidationError`` if the envelope is not restorable."""
    if not isinstance(payload, dict):
        raise ValidationError("Backup must be a JSON object.")
    fmt = payload.get("format")
    if fmt != FORMAT:
        raise ValidationError(f"Not a {FORMAT} file.")
    version = payload.get("version")
    if not isinstance(version, int):
        raise ValidationError("Backup is missing a version number.")
    if version > VERSION:
        raise ValidationError(
            f"Backup was created by a newer app version ({version}); "
            f"this build supports up to version {VERSION}."
        )
    if version < 1:
        raise ValidationError("Backup version is not supported.")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValidationError("Backup is missing its data section.")
    missing = sorted(REQUIRED_TABLES - set(data.keys()))
    if missing:
        raise ValidationError(
            "Backup is missing data for: " + ", ".join(missing) + "."
        )
    for table in TABLE_ORDER:
        rows = data[table]
        if not isinstance(rows, list):
            raise ValidationError(f"Backup section '{table}' must be a list.")
    profiles = data.get("profiles") or []
    if not profiles:
        raise ValidationError("Backup must include a profile row to be restored.")


def count_rows(data: dict) -> dict[str, int]:
    """Per-table row counts for a validated payload's ``data`` section."""
    return {table: len(data.get(table) or []) for table in TABLE_ORDER}