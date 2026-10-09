"""Reusable SQLAlchemy column types."""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Enum as SAEnum


def string_enum(enum_cls: type[StrEnum]) -> SAEnum:
    """Store a Python ``StrEnum`` as plain VARCHAR + CHECK constraints.

    SQLite has no native enums; storing the enum *value* (e.g. ``"checking"``)
    keeps rows readable and JSON friendly while SQLAlchemy still validates
    values on write.
    """
    return SAEnum(
        enum_cls,
        native_enum=False,
        values_callable=lambda member: [item.value for item in member],
        validate_strings=True,
        create_constraint=True,
    )
