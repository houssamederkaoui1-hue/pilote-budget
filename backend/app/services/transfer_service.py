"""Transfer CRUD (money moving between accounts)."""

from __future__ import annotations

from datetime import date as date_type

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import TransferStatus
from app.domain.errors import NotFoundError, ValidationError
from app.models.account import Account
from app.models.transfer import Transfer
from app.services.balance_service import BalanceService
from app.services.validators import (
    validate_account,
    validate_amount,
    validate_date,
    validate_description,
)


class TransferService:
    def __init__(self, session: Session):
        self.session = session
        self.balances = BalanceService(session)

    def get(self, transfer_id: int) -> Transfer:
        transfer = self.session.get(Transfer, transfer_id)
        if transfer is None:
            raise NotFoundError(f"Transfer {transfer_id} not found")
        return transfer

    def create(
        self,
        *,
        source_account_id: int,
        destination_account_id: int,
        amount: float,
        date: date_type,
        description: str = "",
        notes: str | None = None,
        status: str | TransferStatus = TransferStatus.COMPLETED,
    ) -> Transfer:
        amount = validate_amount(amount)
        transfer_date = validate_date(date)
        source = validate_account(self.session, source_account_id, require_active=True)
        destination = validate_account(
            self.session, destination_account_id, require_active=True
        )
        if source.id == destination.id:
            raise ValidationError("Transfer source and destination must be different accounts")

        transfer = Transfer(
            source_account_id=source.id,
            destination_account_id=destination.id,
            amount=amount,
            date=transfer_date,
            description=validate_description(description),
            notes=(notes or "").strip() or None,
            status=self._coerce_status(status),
        )
        self.session.add(transfer)
        self.session.flush()
        self.balances.sync([source.id, destination.id])
        return transfer

    def update(self, transfer_id: int, **fields) -> Transfer:
        transfer = self.get(transfer_id)
        affected = {transfer.source_account_id, transfer.destination_account_id}

        if "amount" in fields and fields["amount"] is not None:
            transfer.amount = validate_amount(fields["amount"])
        if "date" in fields and fields["date"] is not None:
            transfer.date = validate_date(fields["date"])
        if "description" in fields and fields["description"] is not None:
            transfer.description = validate_description(fields["description"])
        if "notes" in fields:
            transfer.notes = (fields["notes"] or "").strip() or None
        if "status" in fields and fields["status"] is not None:
            transfer.status = self._coerce_status(fields["status"])

        source_id = fields.get("source_account_id", transfer.source_account_id)
        destination_id = fields.get(
            "destination_account_id", transfer.destination_account_id
        )
        if source_id is not None:
            source = validate_account(self.session, source_id, require_active=True)
            transfer.source_account_id = source.id
            affected.add(source.id)
        if destination_id is not None:
            destination = validate_account(
                self.session, destination_id, require_active=True
            )
            transfer.destination_account_id = destination.id
            affected.add(destination.id)
        if transfer.source_account_id == transfer.destination_account_id:
            raise ValidationError("Transfer source and destination must be different accounts")

        self.session.flush()
        self.balances.sync(list(affected))
        return transfer

    def delete(self, transfer_id: int) -> None:
        transfer = self.get(transfer_id)
        affected = [transfer.source_account_id, transfer.destination_account_id]
        self.session.delete(transfer)
        self.session.flush()
        self.balances.sync(affected)

    @staticmethod
    def _coerce_status(value: str | TransferStatus) -> TransferStatus:
        if isinstance(value, TransferStatus):
            return value
        try:
            return TransferStatus(value)
        except ValueError as exc:
            raise ValidationError(f"Unknown transfer status: {value}") from exc

    @staticmethod
    def active_account_ids(session: Session) -> list[int]:  # pragma: no cover - helper
        return list(session.scalars(select(Account.id).where(Account.active.is_(True))))
