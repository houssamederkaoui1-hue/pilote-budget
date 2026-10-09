"""Transfers between accounts."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, MoneyAmount, TimestampMixin
from app.db.types import string_enum
from app.domain.enums import TransferStatus

if TYPE_CHECKING:
    from app.models.account import Account
    from app.models.transaction import Transaction


class Transfer(Base, TimestampMixin):
    """Money moved from one account to another.

    The transfer table is the authoritative store for transfers: it holds the
    source, destination, amount, date and description. Balances read it
    directly (source ``-amount``, destination ``+amount``) alongside the
    transactions table, so a transfer is never an income or expense row.

    ``source_transaction_id`` / ``destination_transaction_id`` stay available
    for a future double-entry posting mode but are intentionally unused for
    now to keep a single source of truth.
    """

    __tablename__ = "transfers"
    __table_args__ = (
        CheckConstraint(
            "source_account_id <> destination_account_id",
            name="distinct_accounts",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    destination_account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    amount: Mapped[MoneyAmount] = mapped_column()
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default="")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TransferStatus] = mapped_column(
        string_enum(TransferStatus), nullable=False, default=TransferStatus.COMPLETED
    )

    source_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True
    )
    destination_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True
    )

    source_account: Mapped[Account] = relationship(
        "Account", foreign_keys=[source_account_id], lazy="selectin"
    )
    destination_account: Mapped[Account] = relationship(
        "Account", foreign_keys=[destination_account_id], lazy="selectin"
    )
    source_transaction: Mapped[Transaction | None] = relationship(
        "Transaction", foreign_keys=[source_transaction_id], lazy="selectin"
    )
    destination_transaction: Mapped[Transaction | None] = relationship(
        "Transaction", foreign_keys=[destination_transaction_id], lazy="selectin"
    )
