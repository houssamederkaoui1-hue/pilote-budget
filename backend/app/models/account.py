"""Bank/cash accounts."""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, MoneyAmount, TimestampMixin
from app.db.types import string_enum
from app.domain.enums import AccountType


class Account(Base, TimestampMixin):
    """A financial account.

    Balance model:
    - ``opening_balance``: the immutable seed balance when the account was added.
    - ``current_balance``: cached running balance maintained by the service
      layer whenever transactions/transfers change (recalculated, never
      accumulated blindly, so imports stay idempotent).

    ``currency`` is optional: when null the account inherits the profile
    currency.
    """

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    type: Mapped[AccountType] = mapped_column(
        string_enum(AccountType), nullable=False, default=AccountType.BANK
    )
    opening_balance: Mapped[MoneyAmount] = mapped_column(default=0.0, server_default="0")
    current_balance: Mapped[MoneyAmount] = mapped_column(default=0.0, server_default="0")
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    import_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
