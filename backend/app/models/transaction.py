"""The transaction ledger."""

from __future__ import annotations

from datetime import date
from typing import Any, TYPE_CHECKING

from sqlalchemy import JSON, Date, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, MoneyAmount, TimestampMixin
from app.db.types import string_enum
from app.domain.enums import TransactionStatus, TransactionType

if TYPE_CHECKING:
    from app.models.account import Account
    from app.models.category import Category


class Transaction(Base, TimestampMixin):
    """A single ledger entry (income or expense).

    ``amount`` is always stored as a positive magnitude; the direction is
    expressed by ``type`` (income/expense/transfer).

    Transfers between accounts are **not** stored here: they live in the
    :class:`~app.models.transfer.Transfer` table and are merged into list
    responses at query time. ``type == "transfer"`` is reserved for the API
    representation of those rows. Balances and income/expense summaries are
    therefore computed from a single direction per table and transfers can
    never leak into income/expense totals.

    Import metadata supports idempotent CSV imports: ``dedupe_key`` holds a
    content fingerprint (or source reference) used to skip duplicate rows.
    """

    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_date_account", "date", "account_id"),
        Index("ix_transactions_type_date", "type", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    type: Mapped[TransactionType] = mapped_column(string_enum(TransactionType), nullable=False)
    amount: Mapped[MoneyAmount] = mapped_column()
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default="")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TransactionStatus] = mapped_column(
        string_enum(TransactionStatus),
        nullable=False,
        default=TransactionStatus.CLEARED,
    )

    # Import metadata (CSV / bank export ingestion)
    import_batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    import_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    account: Mapped[Account] = relationship("Account", lazy="selectin")
    category: Mapped[Category | None] = relationship("Category", lazy="selectin")
