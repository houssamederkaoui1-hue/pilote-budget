"""Account CRUD."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.enums import AccountType
from app.domain.errors import ConflictError, NotFoundError, ValidationError
from app.models.account import Account
from app.models.debt import Debt
from app.models.goal import Goal
from app.models.recurring import RecurringTransaction
from app.models.transaction import Transaction
from app.models.transfer import Transfer
from app.services.balance_service import BalanceService


def _clean_name(name: str | None) -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        raise ValidationError("Account name is required")
    if len(cleaned) > 120:
        raise ValidationError("Account name must be 120 characters or fewer")
    return cleaned


class AccountService:
    def __init__(self, session: Session):
        self.session = session
        self.balances = BalanceService(session)

    # -- reads ------------------------------------------------------------

    def list(self, *, include_archived: bool = False, type: str | None = None) -> list[Account]:
        """Accounts ordered by name with balances computed from the ledger."""
        stmt = select(Account)
        if not include_archived:
            stmt = stmt.where(Account.active.is_(True))
        if type:
            try:
                account_type = AccountType(type)
            except ValueError as exc:
                raise ValidationError(f"Unknown account type: {type}") from exc
            stmt = stmt.where(Account.type == account_type)
        accounts = list(self.session.scalars(stmt.order_by(Account.name)))

        computed = self.balances.compute_all()
        for account in accounts:
            account.current_balance = computed.get(account.id, 0.0)
        return accounts

    def get(self, account_id: int) -> Account:
        account = self.session.get(Account, account_id)
        if account is None:
            raise NotFoundError(f"Account {account_id} not found")
        account.current_balance = self.balances.compute_all().get(account.id, 0.0)
        return account

    # -- writes -----------------------------------------------------------

    def create(
        self,
        *,
        name: str,
        type: str | AccountType = AccountType.BANK,
        opening_balance: float = 0.0,
        currency: str | None = None,
        description: str | None = None,
        active: bool = True,
    ) -> Account:
        cleaned_name = _clean_name(name)
        self._ensure_unique_name(cleaned_name)
        account_type = self._coerce_type(type)

        account = Account(
            name=cleaned_name,
            type=account_type,
            opening_balance=round(float(opening_balance), 2),
            current_balance=round(float(opening_balance), 2),
            currency=(currency or None) and currency.upper(),
            description=(description or "").strip() or None,
            active=active,
        )
        self.session.add(account)
        self.session.flush()
        self.balances.sync([account.id])
        return account

    def update(self, account_id: int, **fields) -> Account:
        account = self.get(account_id)

        if "name" in fields and fields["name"] is not None:
            cleaned_name = _clean_name(fields["name"])
            if cleaned_name.lower() != account.name.lower():
                self._ensure_unique_name(cleaned_name, exclude_id=account_id)
            account.name = cleaned_name
        if "type" in fields and fields["type"] is not None:
            account.type = self._coerce_type(fields["type"])
        if "opening_balance" in fields and fields["opening_balance"] is not None:
            account.opening_balance = round(float(fields["opening_balance"]), 2)
        if "currency" in fields:
            account.currency = fields["currency"].upper() if fields["currency"] else None
        if "description" in fields:
            account.description = (fields["description"] or "").strip() or None
        if "active" in fields and fields["active"] is not None:
            account.active = bool(fields["active"])

        self.session.flush()
        self.balances.sync([account.id])
        return account

    def archive(self, account_id: int, *, active: bool = False) -> Account:
        """Deactivate/reactivate an account (its history is kept)."""
        return self.update(account_id, active=active)

    def delete(self, account_id: int) -> None:
        """Hard delete. Refuses when any record references the account."""
        account = self.get(account_id)
        references = self._reference_counts(account_id)
        if any(references.values()):
            used = ", ".join(name for name, count in references.items() if count)
            raise ConflictError(
                f"Account is referenced by {used}; archive it instead of deleting"
            )
        self.session.delete(account)
        self.session.flush()

    # -- helpers ----------------------------------------------------------

    def _ensure_unique_name(self, name: str, exclude_id: int | None = None) -> None:
        stmt = select(func.count()).select_from(Account).where(func.lower(Account.name) == name.lower())
        if exclude_id is not None:
            stmt = stmt.where(Account.id != exclude_id)
        if self.session.scalar(stmt):
            raise ConflictError(f"An account named '{name}' already exists")

    @staticmethod
    def _coerce_type(value: str | AccountType) -> AccountType:
        if isinstance(value, AccountType):
            return value
        try:
            return AccountType(value)
        except ValueError as exc:
            allowed = ", ".join(member.value for member in AccountType)
            raise ValidationError(f"Unknown account type '{value}' (allowed: {allowed})") from exc

    def _reference_counts(self, account_id: int) -> dict[str, int]:
        def count(stmt) -> int:
            return int(self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)

        return {
            "transactions": count(
                select(Transaction).where(Transaction.account_id == account_id)
            ),
            "transfers": count(
                select(Transfer).where(
                    (Transfer.source_account_id == account_id)
                    | (Transfer.destination_account_id == account_id)
                )
            ),
            "recurring transactions": count(
                select(RecurringTransaction).where(RecurringTransaction.account_id == account_id)
            ),
            "goals": count(select(Goal).where(Goal.account_id == account_id)),
            "debts": count(select(Debt).where(Debt.account_id == account_id)),
        }
