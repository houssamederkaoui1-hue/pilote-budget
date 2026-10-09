"""SQLAlchemy declarative base and shared mixins."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from sqlalchemy import DateTime, MetaData, Numeric, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Fixed precision numeric used for every monetary amount. SQLite stores it as
# a float; ``asdecimal=False`` returns plain floats so the API can serialise
# directly to JSON without Decimal conversion warnings.
MoneyType = Numeric(19, 4, asdecimal=False)
MoneyAmount = Annotated[float, MoneyType]
OptionalMoneyAmount = Annotated[float | None, MoneyType]


def utcnow() -> datetime:
    """Naive UTC timestamp (SQLite stores no timezone info)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        default=utcnow,
        onupdate=utcnow,
    )
