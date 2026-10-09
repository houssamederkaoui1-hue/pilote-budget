"""Financial overview: assets, liabilities and net worth.

Net worth is derived from the single source of truth (account balances,
positive = asset, negative = liability), plus the debt ledger.

Double-counting rule: a debt **linked** to a liability account is already
reflected in that account's negative balance, so only the uncovered part
(``remaining - covered``) is counted again; an **unlinked** debt contributes
its full remaining balance. This keeps credit-card and loan liabilities
counted exactly once no matter how they are tracked.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.debt import Debt
from app.services.balance_service import BalanceService


def _round0(value: float | None) -> float:
    return round(float(value or 0.0), 2)


class OverviewService:
    def __init__(self, session: Session):
        self.session = session
        self.balances = BalanceService(session)

    def get(self) -> dict:
        account_balances = self.balances.compute_all()

        account_assets = 0.0
        account_liabilities = 0.0
        for balance in account_balances.values():
            if balance > 0:
                account_assets += balance
            elif balance < 0:
                account_liabilities += -balance

        debts = self.session.scalars(select(Debt).where(Debt.active.is_(True))).all()
        debt_liabilities = 0.0
        for debt in debts:
            remaining = float(debt.remaining_amount)
            if debt.account_id is None:
                debt_liabilities += remaining
                continue
            covered = max(0.0, -account_balances.get(debt.account_id, 0.0))
            debt_liabilities += max(0.0, remaining - covered)

        total_assets = _round0(account_assets)
        total_liabilities = _round0(account_liabilities + debt_liabilities)
        return {
            "total_assets": total_assets,
            "total_liabilities": total_liabilities,
            "net_worth": _round0(total_assets - total_liabilities),
            "account_assets": total_assets,
            "account_liabilities": _round0(account_liabilities),
            "debt_liabilities": _round0(debt_liabilities),
        }