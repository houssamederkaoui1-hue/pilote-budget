"""Transaction CRUD, filtering and list merging.

Transfers are stored in their own table. The list endpoint merges both
sources with a SQL ``UNION ALL`` projection, applies ``LIMIT/OFFSET`` at the
database and totals rows with ``COUNT`` — only the visible page's entities are
hydrated. ``iter_rows`` (CSV export) still streams every match in memory.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type

from sqlalchemy import func, literal, or_, select
from sqlalchemy.orm import Session

from app.domain.enums import TransactionStatus, TransactionType, TransferStatus
from app.domain.errors import NotFoundError, ValidationError
from app.models.transaction import Transaction
from app.models.transfer import Transfer
from app.services.balance_service import BalanceService
from app.services.transfer_service import TransferService
from app.services.validators import (
    validate_account,
    validate_amount,
    validate_category,
    validate_date,
    validate_description,
    validate_enum,
    validate_notes,
)

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500


@dataclass
class TransactionFilters:
    q: str | None = None
    date_from: date_type | None = None
    date_to: date_type | None = None
    account_id: int | None = None
    category_id: int | None = None
    type: str | None = None
    limit: int = DEFAULT_PAGE_SIZE
    offset: int = 0

    def normalized(self) -> "TransactionFilters":
        if self.type is not None and self.type not in {
            TransactionType.INCOME.value,
            TransactionType.EXPENSE.value,
            TransactionType.TRANSFER.value,
        }:
            raise ValidationError(
                f"Unknown transaction type filter '{self.type}' "
                "(allowed: income, expense, transfer)"
            )
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValidationError("date_from must be on or before date_to")
        limit = max(1, min(int(self.limit), MAX_PAGE_SIZE))
        offset = max(0, int(self.offset))
        return TransactionFilters(
            q=(self.q or "").strip() or None,
            date_from=self.date_from,
            date_to=self.date_to,
            account_id=self.account_id,
            category_id=self.category_id,
            type=self.type,
            limit=limit,
            offset=offset,
        )


def serialize_transaction(tx: Transaction) -> dict:
    return {
        "id": tx.id,
        "entity": "transaction",
        "type": tx.type.value,
        "amount": tx.amount,
        "date": tx.date,
        "description": tx.description,
        "notes": tx.notes,
        "status": tx.status.value,
        "account_id": tx.account_id,
        "account_name": tx.account.name if tx.account else None,
        "category_id": tx.category_id,
        "category_name": tx.category.name if tx.category else None,
        "destination_account_id": None,
        "destination_account_name": None,
        "created_at": tx.created_at,
        "updated_at": tx.updated_at,
    }


def serialize_transfer(tr: Transfer) -> dict:
    return {
        "id": tr.id,
        "entity": "transfer",
        "type": TransactionType.TRANSFER.value,
        "amount": tr.amount,
        "date": tr.date,
        "description": tr.description,
        "notes": tr.notes,
        "status": tr.status.value,
        "account_id": tr.source_account_id,
        "account_name": tr.source_account.name if tr.source_account else None,
        "category_id": None,
        "category_name": None,
        "destination_account_id": tr.destination_account_id,
        "destination_account_name": (
            tr.destination_account.name if tr.destination_account else None
        ),
        "created_at": tr.created_at,
        "updated_at": tr.updated_at,
    }


class TransactionService:
    def __init__(self, session: Session):
        self.session = session
        self.balances = BalanceService(session)
        self.transfers = TransferService(session)

    # -- reads ------------------------------------------------------------

    def get(self, transaction_id: int) -> Transaction:
        transaction = self.session.get(Transaction, transaction_id)
        if transaction is None:
            raise NotFoundError(f"Transaction {transaction_id} not found")
        return transaction

    def list(self, filters: TransactionFilters | None = None) -> dict:
        filters = (filters or TransactionFilters()).normalized()
        return self._paged(filters)

    def _paged(self, filters: TransactionFilters) -> dict:
        """Paged merge of transactions + transfers, sliced and counted in SQL."""
        include_transactions = filters.type in (
            None,
            TransactionType.INCOME.value,
            TransactionType.EXPENSE.value,
        )
        include_transfers = filters.type in (None, TransactionType.TRANSFER.value)
        # Transfers carry no category, so a category filter only matches
        # plain transactions.
        if filters.category_id is not None:
            include_transfers = False

        projections: list[Select] = []
        total = 0
        if include_transactions:
            tx_clauses = self._transaction_clauses(filters)
            total += (
                self.session.scalar(
                    select(func.count()).select_from(Transaction).where(*tx_clauses)
                )
                or 0
            )
            projections.append(
                select(
                    literal("transaction").label("entity"),
                    Transaction.id.label("id"),
                    Transaction.date.label("date"),
                    Transaction.created_at.label("created_at"),
                ).where(*tx_clauses)
            )
        if include_transfers:
            tr_clauses = self._transfer_clauses(filters)
            total += (
                self.session.scalar(
                    select(func.count()).select_from(Transfer).where(*tr_clauses)
                )
                or 0
            )
            projections.append(
                select(
                    literal("transfer").label("entity"),
                    Transfer.id.label("id"),
                    Transfer.date.label("date"),
                    Transfer.created_at.label("created_at"),
                ).where(*tr_clauses)
            )

        if not projections:
            return {
                "items": [],
                "total": 0,
                "limit": filters.limit,
                "offset": filters.offset,
            }

        merged = projections[0]
        for projection in projections[1:]:
            merged = merged.union_all(projection)
        page = merged.subquery()

        keys = self.session.execute(
            select(page.c.entity, page.c.id)
            .order_by(
                page.c.date.desc(),
                page.c.created_at.desc(),
                page.c.entity.asc(),
                page.c.id.desc(),
            )
            .offset(filters.offset)
            .limit(filters.limit)
        ).all()

        tx_ids = [row.id for row in keys if row.entity == "transaction"]
        tr_ids = [row.id for row in keys if row.entity == "transfer"]
        transactions = self.session.scalars(
            select(Transaction).where(Transaction.id.in_(tx_ids))
        ).all() if tx_ids else []
        transfers = self.session.scalars(
            select(Transfer).where(Transfer.id.in_(tr_ids))
        ).all() if tr_ids else []
        tx_by_id = {tx.id: tx for tx in transactions}
        tr_by_id = {tr.id: tr for tr in transfers}

        items: list[dict] = []
        for row in keys:
            if row.entity == "transaction":
                transaction = tx_by_id.get(row.id)
                if transaction is not None:
                    items.append(serialize_transaction(transaction))
            else:
                transfer = tr_by_id.get(row.id)
                if transfer is not None:
                    items.append(serialize_transfer(transfer))
        return {
            "items": items,
            "total": total,
            "limit": filters.limit,
            "offset": filters.offset,
        }

    def iter_rows(self, filters: TransactionFilters | None = None) -> list[dict]:
        """Every matching row, unpaginated (used by CSV export)."""
        return self._collect((filters or TransactionFilters()).normalized())

    def _collect(self, filters: TransactionFilters) -> list[dict]:
        include_transactions = filters.type in (
            None,
            TransactionType.INCOME.value,
            TransactionType.EXPENSE.value,
        )
        include_transfers = filters.type in (None, TransactionType.TRANSFER.value)
        # Transfers carry no category, so a category filter only matches
        # plain transactions.
        if filters.category_id is not None:
            include_transfers = False

        rows: list[dict] = []
        if include_transactions:
            stmt = select(Transaction).where(*self._transaction_clauses(filters))
            rows.extend(
                serialize_transaction(tx) for tx in self.session.scalars(stmt).all()
            )
        if include_transfers:
            stmt = select(Transfer).where(*self._transfer_clauses(filters))
            rows.extend(
                serialize_transfer(tr) for tr in self.session.scalars(stmt).all()
            )

        rows.sort(
            key=lambda row: (
                -row["date"].toordinal(),
                -row["created_at"].timestamp(),
                row["entity"],
                -row["id"],
            )
        )
        return rows

    def summary(self, date_from: date_type | None = None, date_to: date_type | None = None) -> dict:
        return self.balances.summary(date_from, date_to)

    # -- writes -----------------------------------------------------------

    def create(
        self,
        *,
        type: str | TransactionType,
        amount: float,
        account_id: int,
        date: date_type,
        category_id: int | None = None,
        destination_account_id: int | None = None,
        description: str = "",
        notes: str | None = None,
        status: str | TransactionStatus = TransactionStatus.CLEARED,
    ):
        transaction_type = validate_enum(type, TransactionType, "transaction type")

        if transaction_type == TransactionType.TRANSFER:
            if destination_account_id is None:
                raise ValidationError("Transfers require a destination account")
            return self.transfers.create(
                source_account_id=account_id,
                destination_account_id=destination_account_id,
                amount=amount,
                date=date,
                description=description,
                notes=notes,
                status=self._coerce_transfer_status(status),
            )

        amount = validate_amount(amount)
        transfer_date = validate_date(date)
        account = validate_account(self.session, account_id, require_active=True)
        category = validate_category(
            self.session, category_id, expected_type=transaction_type.value
        )
        if destination_account_id is not None:
            raise ValidationError(
                "destination_account_id is only valid for transfer transactions"
            )

        transaction = Transaction(
            account_id=account.id,
            category_id=category.id if category else None,
            type=transaction_type,
            amount=amount,
            date=transfer_date,
            description=validate_description(description),
            notes=validate_notes(notes),
            status=validate_enum(status, TransactionStatus, "status"),
        )
        self.session.add(transaction)
        self.session.flush()
        self.balances.sync([account.id])
        return transaction

    def update(self, transaction_id: int, **fields) -> Transaction:
        transaction = self.get(transaction_id)
        affected = {transaction.account_id}

        if "type" in fields and fields["type"] is not None:
            new_type = validate_enum(fields["type"], TransactionType, "transaction type")
            if new_type != transaction.type:
                raise ValidationError(
                    "Transaction type cannot be changed; delete it and create a new one"
                )
        if "amount" in fields and fields["amount"] is not None:
            transaction.amount = validate_amount(fields["amount"])
        if "date" in fields and fields["date"] is not None:
            transaction.date = validate_date(fields["date"])
        if "description" in fields and fields["description"] is not None:
            transaction.description = validate_description(fields["description"])
        if "notes" in fields:
            transaction.notes = validate_notes(fields["notes"])
        if "status" in fields and fields["status"] is not None:
            transaction.status = validate_enum(fields["status"], TransactionStatus, "status")
        if "account_id" in fields and fields["account_id"] is not None:
            account = validate_account(self.session, fields["account_id"], require_active=True)
            transaction.account_id = account.id
            affected.add(account.id)
        if "category_id" in fields:
            category = validate_category(
                self.session,
                fields["category_id"],
                expected_type=transaction.type.value,
            )
            transaction.category_id = category.id if category else None
        if "destination_account_id" in fields and fields["destination_account_id"] is not None:
            raise ValidationError("destination_account_id is not valid on a transaction")

        self.session.flush()
        self.balances.sync(list(affected))
        return transaction

    def delete(self, transaction_id: int) -> None:
        transaction = self.get(transaction_id)
        account_id = transaction.account_id
        self.session.delete(transaction)
        self.session.flush()
        self.balances.sync([account_id])


    @staticmethod
    def _coerce_transfer_status(value) -> TransferStatus:
        """Map a transaction-style status onto transfer statuses (and accept native ones)."""
        if isinstance(value, TransferStatus):
            return value
        aliases = {
            "cleared": TransferStatus.COMPLETED,
            "reconciled": TransferStatus.COMPLETED,
            "void": TransferStatus.CANCELLED,
            "pending": TransferStatus.PENDING,
            "completed": TransferStatus.COMPLETED,
            "cancelled": TransferStatus.CANCELLED,
        }
        mapped = aliases.get(str(value))
        if mapped is None:
            allowed = ", ".join(sorted(aliases))
            raise ValidationError(f"Unknown transfer status '{value}' (allowed: {allowed})")
        return mapped

    # -- query builders ---------------------------------------------------


    @staticmethod
    def _transaction_clauses(filters: TransactionFilters) -> list:
        clauses = []
        if filters.date_from is not None:
            clauses.append(Transaction.date >= filters.date_from)
        if filters.date_to is not None:
            clauses.append(Transaction.date <= filters.date_to)
        if filters.account_id is not None:
            clauses.append(Transaction.account_id == filters.account_id)
        if filters.category_id is not None:
            clauses.append(Transaction.category_id == filters.category_id)
        if filters.type is not None:
            clauses.append(Transaction.type == TransactionType(filters.type))
        if filters.q:
            pattern = f"%{filters.q.lower()}%"
            clauses.append(
                or_(
                    func.lower(Transaction.description).like(pattern),
                    func.lower(Transaction.notes).like(pattern),
                )
            )
        return clauses

    @staticmethod
    def _transfer_clauses(filters: TransactionFilters) -> list:
        clauses = []
        if filters.date_from is not None:
            clauses.append(Transfer.date >= filters.date_from)
        if filters.date_to is not None:
            clauses.append(Transfer.date <= filters.date_to)
        if filters.account_id is not None:
            clauses.append(
                or_(
                    Transfer.source_account_id == filters.account_id,
                    Transfer.destination_account_id == filters.account_id,
                )
            )
        if filters.q:
            pattern = f"%{filters.q.lower()}%"
            clauses.append(
                or_(
                    func.lower(Transfer.description).like(pattern),
                    func.lower(Transfer.notes).like(pattern),
                )
            )
        return clauses
