"""Single source of truth for balances and ledger summaries.

Every balance in the application comes from this module:

- ``transactions`` contribute income (``+amount``) and expense (``-amount``);
  void rows are ignored.
- ``transfers`` contribute ``-amount`` to the source account and ``+amount``
  to the destination account; cancelled transfers are ignored. They are
  deliberately **never** part of income/expense summaries.

``Account.current_balance`` is only a cached projection: it is refreshed
exclusively by :meth:`BalanceService.sync`, so the formula lives in exactly
one place. Reads go through the computed value, never the cache.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.domain.enums import (
    TransactionStatus,
    TransactionType,
    TransferStatus,
)
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.transfer import Transfer

POSTED_TRANSACTION_STATUSES = (
    TransactionStatus.PENDING,
    TransactionStatus.CLEARED,
    TransactionStatus.RECONCILED,
)
POSTED_TRANSFER_STATUSES = (
    TransferStatus.PENDING,
    TransferStatus.COMPLETED,
)


def _round(value: float | None) -> float:
    return round(float(value or 0.0), 2)


class BalanceService:
    def __init__(self, session: Session):
        self.session = session

    # -- computation -----------------------------------------------------

    def _transaction_deltas(self) -> dict[int, float]:
        """account_id -> signed income/expense delta (void rows excluded)."""
        rows = self.session.execute(
            select(
                Transaction.account_id,
                func.sum(
                    case(
                        (Transaction.type == TransactionType.INCOME, Transaction.amount),
                        (Transaction.type == TransactionType.EXPENSE, -Transaction.amount),
                        else_=0,
                    )
                ),
            )
            .where(Transaction.status.in_(POSTED_TRANSACTION_STATUSES))
            .group_by(Transaction.account_id)
        ).all()
        return {account_id: _round(total) for account_id, total in rows}

    def _transfer_deltas(self) -> tuple[dict[int, float], dict[int, float]]:
        """account_id -> (incoming, outgoing) transfer totals."""
        outgoing_rows = self.session.execute(
            select(Transfer.source_account_id, func.sum(Transfer.amount))
            .where(Transfer.status.in_(POSTED_TRANSFER_STATUSES))
            .group_by(Transfer.source_account_id)
        ).all()
        incoming_rows = self.session.execute(
            select(Transfer.destination_account_id, func.sum(Transfer.amount))
            .where(Transfer.status.in_(POSTED_TRANSFER_STATUSES))
            .group_by(Transfer.destination_account_id)
        ).all()
        return (
            {account_id: _round(total) for account_id, total in incoming_rows},
            {account_id: _round(total) for account_id, total in outgoing_rows},
        )

    def compute_all(self) -> dict[int, float]:
        """account_id -> computed balance for every account (archived too)."""
        accounts = self.session.scalars(select(Account)).all()
        tx_deltas = self._transaction_deltas()
        incoming, outgoing = self._transfer_deltas()

        balances: dict[int, float] = {}
        for account in accounts:
            balances[account.id] = _round(
                account.opening_balance
                + tx_deltas.get(account.id, 0.0)
                + incoming.get(account.id, 0.0)
                - outgoing.get(account.id, 0.0)
            )
        return balances

    def compute(self, account_id: int) -> float:
        balances = self.compute_all()
        if account_id not in balances:
            from app.domain.errors import NotFoundError

            raise NotFoundError(f"Account {account_id} not found")
        return balances[account_id]

    def compute_as_of(self, on: date) -> dict[int, float]:
        """account_id -> balance as of the end of ``on`` (inclusive).

        Reconstructs every account's balance from the opening seed plus posted
        transactions and transfers with ``date <= on``. This is how historical
        net worth is derived from real ledger data only (never fabricated).
        """
        accounts = self.session.scalars(select(Account)).all()

        tx_clauses = [Transaction.status.in_(POSTED_TRANSACTION_STATUSES), Transaction.date <= on]
        tx_rows = self.session.execute(
            select(
                Transaction.account_id,
                func.sum(
                    case(
                        (Transaction.type == TransactionType.INCOME, Transaction.amount),
                        (Transaction.type == TransactionType.EXPENSE, -Transaction.amount),
                        else_=0,
                    )
                ),
            )
            .where(*tx_clauses)
            .group_by(Transaction.account_id)
        ).all()
        tx_deltas = {account_id: _round(total) for account_id, total in tx_rows}

        tr_clauses = [Transfer.status.in_(POSTED_TRANSFER_STATUSES), Transfer.date <= on]
        outgoing_rows = self.session.execute(
            select(Transfer.source_account_id, func.sum(Transfer.amount))
            .where(*tr_clauses)
            .group_by(Transfer.source_account_id)
        ).all()
        incoming_rows = self.session.execute(
            select(Transfer.destination_account_id, func.sum(Transfer.amount))
            .where(*tr_clauses)
            .group_by(Transfer.destination_account_id)
        ).all()
        outgoing = {account_id: _round(total) for account_id, total in outgoing_rows}
        incoming = {account_id: _round(total) for account_id, total in incoming_rows}

        balances: dict[int, float] = {}
        for account in accounts:
            balances[account.id] = _round(
                account.opening_balance
                + tx_deltas.get(account.id, 0.0)
                + incoming.get(account.id, 0.0)
                - outgoing.get(account.id, 0.0)
            )
        return balances

    # -- cache maintenance ------------------------------------------------

    def sync(self, account_ids: list[int] | None = None) -> dict[int, float]:
        """Refresh the cached ``current_balance`` column for given accounts.

        With ``account_ids=None`` every account is refreshed. Returns the
        balances that were written.
        """
        balances = self.compute_all()
        if account_ids is None:
            targets = list(balances)
        else:
            targets = [account_id for account_id in set(account_ids) if account_id in balances]

        accounts = self.session.scalars(
            select(Account).where(Account.id.in_(targets))
        ).all()
        for account in accounts:
            account.current_balance = balances[account.id]
        self.session.flush()
        return {account.id: balances[account.id] for account in accounts}

    # -- summaries (income/expense never include transfers) ---------------

    def summary(
        self, date_from: date | None = None, date_to: date | None = None
    ) -> dict[str, float]:
        """Income/expense/net for a period plus transfer volumes."""
        tx_clauses = [Transaction.status.in_(POSTED_TRANSACTION_STATUSES)]
        if date_from is not None:
            tx_clauses.append(Transaction.date >= date_from)
        if date_to is not None:
            tx_clauses.append(Transaction.date <= date_to)

        income, expense = self.session.execute(
            select(
                func.sum(
                    case(
                        (Transaction.type == TransactionType.INCOME, Transaction.amount),
                        else_=0,
                    )
                ),
                func.sum(
                    case(
                        (Transaction.type == TransactionType.EXPENSE, Transaction.amount),
                        else_=0,
                    )
                ),
            ).where(*tx_clauses)
        ).one()

        tr_clauses = [Transfer.status.in_(POSTED_TRANSFER_STATUSES)]
        if date_from is not None:
            tr_clauses.append(Transfer.date >= date_from)
        if date_to is not None:
            tr_clauses.append(Transfer.date <= date_to)

        transfer_volume = self.session.execute(
            select(func.sum(Transfer.amount)).where(*tr_clauses)
        ).scalar()

        income_value = _round(income)
        expense_value = _round(expense)
        return {
            "income": income_value,
            "expense": expense_value,
            "net": _round(income_value - expense_value),
            "transfer_volume": _round(transfer_volume),
        }
