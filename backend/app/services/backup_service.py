"""Backup / restore service.

Export dumps every table to a validated envelope; restore deletes all rows and
re-inserts the backup's rows inside a single transaction (rolled back on any
failure). All rows are re-parented by their original ids so cross-table
references stay intact.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, JSON, Numeric
from sqlalchemy.orm import Session

from app.domain.backup import FORMAT, TABLE_ORDER, VERSION, count_rows, validate_envelope
from app.domain.errors import ValidationError
from app.models import (
    Account,
    Budget,
    BudgetAllocation,
    Category,
    Debt,
    Goal,
    Profile,
    RecurringTransaction,
    Transaction,
    Transfer,
)

SPECS: list[tuple[str, object]] = [
    ("profiles", Profile),
    ("categories", Category),
    ("accounts", Account),
    ("budget_allocations", BudgetAllocation),
    ("goals", Goal),
    ("debts", Debt),
    ("budgets", Budget),
    ("transactions", Transaction),
    ("transfers", Transfer),
    ("recurring_transactions", RecurringTransaction),
]
_BY_TABLE = {name: model for name, model in SPECS}


def _dump_value(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _coerce(value, coltype):
    if value is None:
        return None
    if isinstance(coltype, DateTime):
        return datetime.fromisoformat(value)
    if isinstance(coltype, Date):
        return date.fromisoformat(value)
    if isinstance(coltype, JSON):
        return value
    if isinstance(coltype, Boolean):
        return bool(value)
    if isinstance(coltype, Integer):
        return int(value)
    if isinstance(coltype, (Float, Numeric)):
        return float(value)
    return value


class BackupService:
    def __init__(self, session: Session):
        self.session = session

    # -- export ---------------------------------------------------------------

    def export(self) -> dict:
        data: dict[str, list[dict]] = {}
        for table in TABLE_ORDER:
            model = _BY_TABLE[table]
            columns = [c.name for c in model.__table__.columns]
            rows = self.session.execute(model.__table__.select()).mappings()
            data[table] = [
                {col: _dump_value(row[col]) for col in columns}
                for row in rows
            ]
        self.session.commit()
        counts = count_rows(data)
        return {
            "format": FORMAT,
            "version": VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "counts": [{"table": k, "rows": v} for k, v in counts.items()],
            "data": data,
        }

    # -- restore ---------------------------------------------------------------

    def validate(self, payload: dict) -> dict:
        validate_envelope(payload)
        self._validate_references(payload)
        counts = count_rows(payload["data"])
        self.session.commit()
        return {
            "valid": True,
            "format": payload["format"],
            "version": payload["version"],
            "counts": [{"table": k, "rows": v} for k, v in counts.items()],
            "message": "Backup is valid "
            f"({sum(counts.values())} rows across {len(counts)} tables).",
        }

    def restore(self, payload: dict, *, confirmed: bool) -> dict:
        """Replace all local data with the backup's rows, atomically."""
        if not confirmed:
            raise ValidationError("Restore must be explicitly confirmed.")
        validate_envelope(payload)
        self._validate_references(payload)
        data = payload["data"]

        try:
            for table in reversed(TABLE_ORDER):
                self.session.execute(_BY_TABLE[table].__table__.delete())
            for table in TABLE_ORDER:
                self._insert_table(_BY_TABLE[table], data[table])
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        counts = count_rows(data)
        self.session.commit()
        return {
            "valid": True,
            "format": payload["format"],
            "version": payload["version"],
            "confirmed": True,
            "counts": [{"table": k, "rows": v} for k, v in counts.items()],
            "message": "Restore complete.",
        }

    def _insert_table(self, model, rows) -> None:
        inserts = list(rows)
        if model is Category:
            roots = [r for r in inserts if r.get("parent_id") is None]
            children = [r for r in inserts if r.get("parent_id") is not None]
            inserts = roots + children
        columns = model.__table__.columns
        for row in inserts:
            values = {}
            for key, value in row.items():
                if key not in columns:
                    continue
                values[key] = _coerce(value, columns[key].type)
            self.session.execute(model.__table__.insert().values(**values))

    def _validate_references(self, payload: dict) -> None:
        """Reject backups whose rows reference ids that do not exist in it."""
        data = payload["data"]
        ids_by_table: dict[str, set[int]] = {}
        for table, rows in data.items():
            if not isinstance(rows, list):
                continue
            ids_by_table[table] = {
                row["id"] for row in rows if isinstance(row, dict) and "id" in row
            }
        for row in data.get("profiles", []):
            ids_by_table.setdefault("profiles", set()).add(row.get("id"))
        for table, model in SPECS:
            table_obj = model.__table__
            for fk in table_obj.foreign_keys:
                source_col = fk.parent.name
                target_table = fk.column.table.name
                target_ids = ids_by_table.get(target_table, set())
                for index, row in enumerate(data.get(table, [])):
                    value = row.get(source_col)
                    if value is not None and value not in target_ids:
                        raise ValidationError(
                            f"Backup row {index} in '{table}' references missing "
                            f"'{target_table}' id {value}."
                        )