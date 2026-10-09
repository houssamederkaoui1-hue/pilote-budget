"""Quick Add service: single-field fast capture with smart defaults.

Uses the Settings defaults (account + per-type category) so a Quick Add can be
submitted with only a description, type and amount. Duplicate detection runs
first and can optionally block same-day entries.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.domain.enums import TransactionType
from app.domain.errors import ValidationError
from app.services.settings_service import SettingsService
from app.services.suggestion_service import SuggestionService
from app.services.transaction_service import TransactionService


class QuickAddService:
    def __init__(self, session: Session):
        self.session = session
        self.settings = SettingsService(session)
        self.suggestions = SuggestionService(session)
        self.transactions = TransactionService(session)

    @staticmethod
    def _category_preference_key(type: TransactionType) -> str:
        if type == TransactionType.INCOME:
            return "default_income_category_id"
        return "default_expense_category_id"

    def resolve_capture(
        self,
        *,
        type: str | TransactionType,
        description: str = "",
        amount: float,
        on: date | None = None,
        account_id: int | None = None,
        category_id: int | None = None,
    ) -> dict:
        """Resolve defaults + suggestions without writing anything."""
        transaction_type = TransactionType(type)
        settings = self.settings.get_settings()
        resolved_account_id = account_id if account_id is not None else settings["default_account_id"]
        resolved_category_id = category_id
        if resolved_category_id is None:
            default_key = self._category_preference_key(transaction_type)
            resolved_category_id = settings.get(default_key)

        suggestions = self.suggestions.suggest_categories(
            description, transaction_type
        )
        if resolved_category_id is None and suggestions:
            resolved_category_id = int(suggestions[0]["category_id"])

        duplicates = self.suggestions.find_duplicates(
            description,
            transaction_type,
            amount,
            on=on,
            account_id=resolved_account_id,
        )
        return {
            "type": transaction_type.value,
            "amount": round(float(amount), 2),
            "date": (on or date.today()),
            "account_id": resolved_account_id,
            "category_id": resolved_category_id,
            "description": description,
            "categories": suggestions,
            "duplicates": duplicates,
        }

    def create(
        self,
        *,
        type: str | TransactionType,
        amount: float,
        description: str = "",
        on: date | None = None,
        account_id: int | None = None,
        category_id: int | None = None,
        notes: str | None = None,
        reject_duplicate: bool = False,
        check_duplicate: bool = True,
    ):
        transaction_type = TransactionType(type)
        resolved = self.resolve_capture(
            type=transaction_type,
            description=description,
            amount=amount,
            on=on,
            account_id=account_id,
            category_id=category_id,
        )
        if check_duplicate and resolved["duplicates"]:
            if reject_duplicate and any(row["same_day"] for row in resolved["duplicates"]):
                from app.domain.errors import ConflictError

                raise ConflictError(
                    "A matching transaction was already logged for this day. "
                    "Reopen and edit it instead of creating a duplicate."
                )
        if resolved["account_id"] is None:
            raise ValidationError(
                "No account for Quick Add. Create an account first, or "
                "Choose a default account in Settings."
            )

        transaction = self.transactions.create(
            type=transaction_type,
            amount=resolved["amount"],
            account_id=resolved["account_id"],
            date=resolved["date"],
            category_id=resolved["category_id"],
            description=resolved["description"],
            notes=notes,
        )
        self.session.commit()
        return {
            "transaction": transaction,
            "duplicates": resolved["duplicates"],
            "categories": resolved["categories"],
        }