"""CSV import workflow: inspect -> preview -> commit (stateless).

The API is intentionally stateless: every call re-sends the file plus the
explicit mapping, so previews can be refreshed freely and no server-side
upload session needs to be tracked. All parsing/normalization lives in
:mod:`app.domain.csv_import`; this service adds database concerns: account
and category resolution, idempotent dedupe and balance synchronisation.
"""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.csv_import import (
    ImportOptions,
    ImportMapping,
    MappingError,
    ParsedRow,
    inspect_csv,
    mapping_from_payload,
    parse_rows,
    read_csv,
    decode_csv,
)
from app.domain.enums import CategoryType, TransactionStatus, TransactionType
from app.domain.errors import NotFoundError, ValidationError
from app.models.account import Account
from app.models.category import Category
from app.models.transaction import Transaction
from app.services.balance_service import BalanceService


class ImportService:
    def __init__(self, session: Session):
        self.session = session
        self.balances = BalanceService(session)

    # -- step 1: inspect ---------------------------------------------------

    def inspect(
        self,
        data: bytes | str,
        *,
        filename: str | None = None,
        encoding: str = "auto",
    ) -> dict:
        try:
            return inspect_csv(data, filename=filename, encoding=encoding)
        except MappingError as exc:
            raise ValidationError(str(exc)) from exc

    # -- step 2: preview ----------------------------------------------------

    def preview(self, data: bytes | str, mapping_payload: dict) -> dict:
        mapping = self._mapping(mapping_payload)
        header, raw_rows, _ = self._read(data, mapping)
        try:
            parsed = parse_rows(header, raw_rows, mapping)
        except MappingError as exc:
            raise ValidationError(str(exc)) from exc

        resolutions = self._resolve(parsed, mapping.options)
        known_keys = self._existing_keys(
            [r["dedupe_key"] for r in resolutions if r["dedupe_key"]]
        )

        rows = []
        valid = invalid = duplicates = 0
        for row, resolution in zip(parsed, resolutions):
            payload = row.as_dict()
            payload.update(resolution)
            payload["duplicate"] = bool(
                resolution["dedupe_key"] and resolution["dedupe_key"] in known_keys
            )
            if payload["duplicate"]:
                duplicates += 1
            elif row.valid:
                valid += 1
            else:
                invalid += 1
            rows.append(payload)

        return {
            "filename": mapping.options.filename,
            "columns": header,
            "rows": rows,
            "counts": {
                "total": len(rows),
                "valid": valid,
                "invalid": invalid,
                "duplicates": duplicates,
            },
        }

    # -- step 3: commit ------------------------------------------------------

    def commit(self, data: bytes | str, mapping_payload: dict) -> dict:
        mapping = self._mapping(mapping_payload)
        header, raw_rows, _ = self._read(data, mapping)
        try:
            parsed = parse_rows(header, raw_rows, mapping)
        except MappingError as exc:
            raise ValidationError(str(exc)) from exc

        resolutions = self._resolve(parsed, mapping.options)
        batch_id = uuid.uuid4().hex
        known_keys = set(
            self._existing_keys(
                [r["dedupe_key"] for r in resolutions if r["dedupe_key"]]
            )
        )

        created = skipped_duplicates = skipped_invalid = 0
        categories_created = 0
        touched_accounts: set[int] = set()
        errors: list[dict] = []

        for row, resolution in zip(parsed, resolutions):
            if not row.valid:
                skipped_invalid += 1
                errors.append({"row_number": row.row_number, "errors": list(row.errors)})
                continue
            if resolution["account_id"] is None:
                skipped_invalid += 1
                errors.append(
                    {
                        "row_number": row.row_number,
                        "errors": ["No account matches this row and no default is set"],
                    }
                )
                continue
            key = resolution["dedupe_key"]
            if key and key in known_keys:
                skipped_duplicates += 1
                continue

            category_id, was_created = self._ensure_category(row, resolution)
            if was_created:
                categories_created += 1

            account_id = resolution["account_id"]
            self.session.add(
                Transaction(
                    account_id=account_id,
                    category_id=category_id,
                    type=TransactionType(row.type),
                    amount=row.amount,
                    date=row.date,
                    description=row.description,
                    status=TransactionStatus.CLEARED,
                    import_batch_id=batch_id,
                    external_id=row.reference,
                    dedupe_key=key,
                    import_metadata={
                        "source": "csv",
                        "filename": mapping.options.filename,
                        "row_number": row.row_number,
                    },
                )
            )
            if key:
                known_keys.add(key)
            touched_accounts.add(account_id)
            created += 1

        self.session.flush()
        if touched_accounts:
            self.balances.sync(sorted(touched_accounts))

        return {
            "batch_id": batch_id,
            "filename": mapping.options.filename,
            "counts": {
                "total": len(parsed),
                "created": created,
                "skipped_duplicates": skipped_duplicates,
                "skipped_invalid": skipped_invalid,
                "categories_created": categories_created,
            },
            "accounts_touched": sorted(touched_accounts),
            "errors": errors,
        }

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _mapping(payload: dict) -> ImportMapping:
        try:
            return mapping_from_payload(payload)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

    def _read(
        self, data: bytes | str, mapping: ImportMapping
    ) -> tuple[list[str], list[list[str]], str]:
        text, encoding = decode_csv(data, mapping.options.encoding)
        header, rows = read_csv(text)
        if not header:
            raise ValidationError("The file is empty or has no header row")
        return header, rows, encoding

    def _resolve(self, parsed: list[ParsedRow], options: ImportOptions) -> list[dict]:
        """Map every parsed row onto real accounts/categories + a dedupe key."""
        accounts = self._accounts_by_name()
        default_account = None
        if options.default_account_id is not None:
            account = self.session.get(Account, options.default_account_id)
            if account is None:
                raise NotFoundError(f"Default account {options.default_account_id} not found")
            if not account.active:
                raise ValidationError(f"Default account '{account.name}' is archived")
            default_account = account
        default_category = None
        if options.default_category_id is not None:
            category = self.session.get(Category, options.default_category_id)
            if category is None:
                raise NotFoundError(f"Default category {options.default_category_id} not found")
            default_category = category

        resolutions = []
        for row in parsed:
            account_id = None
            account_name = None
            if row.account_name:
                account = accounts.get(row.account_name.lower())
                if account is not None:
                    account_id, account_name = account.id, account.name
            if account_id is None:
                if default_account is not None:
                    account_id, account_name = default_account.id, default_account.name
                elif row.valid:
                    if row.account_name:
                        row.errors.append(
                            f"Unknown account '{row.account_name}' and no default account is set"
                        )
                    else:
                        row.errors.append(
                            "No account for this row and no default account is set"
                        )

            category_name = row.category_name or (
                default_category.name if default_category else None
            )
            resolutions.append(
                {
                    "account_id": account_id,
                    "account_name": account_name,
                    "category_name": category_name,
                    "category_state": self._category_state(row),
                    "default_category_id": (
                        default_category.id
                        if not row.category_name and default_category
                        else None
                    ),
                    "dedupe_key": self._dedupe_key(row, account_id),
                }
            )
        return resolutions

    def _category_state(self, row: ParsedRow) -> str:
        if not row.category_name or not row.type:
            return "none"
        existing = self.session.scalars(
            select(Category).where(
                Category.name.ilike(row.category_name),
                Category.type == CategoryType(row.type),
            )
        ).first()
        return "existing" if existing else "new"

    def _ensure_category(self, row: ParsedRow, resolution: dict) -> tuple[int | None, bool]:
        if row.category_name:
            existing = self.session.scalars(
                select(Category).where(
                    Category.name.ilike(row.category_name),
                    Category.type == CategoryType(row.type),
                )
            ).first()
            if existing is not None:
                return existing.id, False
            category = Category(name=row.category_name.strip()[:120], type=CategoryType(row.type))
            self.session.add(category)
            self.session.flush()
            return category.id, True
        if resolution.get("default_category_id") is not None:
            return resolution["default_category_id"], False
        return None, False

    def _accounts_by_name(self) -> dict[str, Account]:
        accounts = self.session.scalars(select(Account).where(Account.active.is_(True))).all()
        return {account.name.lower(): account for account in accounts}

    def _existing_keys(self, keys: list[str]) -> set[str]:
        unique = [key for key in dict.fromkeys(keys) if key]
        if not unique:
            return set()
        return set(
            self.session.scalars(
                select(Transaction.dedupe_key).where(Transaction.dedupe_key.in_(unique))
            ).all()
        )

    @staticmethod
    def _dedupe_key(row: ParsedRow, account_id: int | None) -> str | None:
        """Reference-based key when the bank provides one, else a content fingerprint."""
        if not row.date or row.amount is None:
            return None
        if row.reference and account_id is not None:
            return f"ref:{account_id}:{row.reference}"[:128]
        payload = "|".join(
            [
                str(account_id),
                row.date.isoformat(),
                row.type,
                f"{row.amount:.2f}",
                row.description.strip().lower(),
            ]
        )
        digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:40]
        return f"fp:{digest}"
