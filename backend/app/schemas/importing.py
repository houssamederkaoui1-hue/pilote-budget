"""CSV import schemas (inspect -> preview -> commit)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.base import APIModel


class FieldColumn(APIModel):
    """Column index (0-based) plus an optional format (e.g. date format)."""

    column: int | None = None
    format: str | None = None


class ImportOptionsPayload(APIModel):
    encoding: str = "auto"
    decimal_separator: Literal[".", ",", "auto"] = "auto"
    amount_mode: Literal["auto", "income", "expense", "flip"] = "auto"
    positive_is: Literal["income", "expense"] = "income"
    default_account_id: int | None = None
    default_category_id: int | None = None
    filename: str | None = None


class ImportMappingPayload(APIModel):
    """Explicit column mapping under ``fields``; unmapped columns are ignored."""

    fields: dict[str, FieldColumn] = Field(default_factory=dict)
    options: ImportOptionsPayload = Field(default_factory=ImportOptionsPayload)


class ColumnSuggestion(APIModel):
    column: int | None = None
    format: str | None = None


class ImportInspectResponse(APIModel):
    filename: str | None
    encoding: str
    delimiter: str
    columns: list[str]
    sample_rows: list[list[str]]
    row_count: int
    suggestions: dict[str, ColumnSuggestion | None]
    date_formats: list[str]
    date_format_candidates: list[str]


class PreviewCounts(APIModel):
    total: int
    valid: int
    invalid: int
    duplicates: int


class PreviewRow(APIModel):
    row_number: int
    date: str | None
    description: str
    amount: float | None
    type: str
    category_name: str | None
    account_name: str | None
    reference: str | None
    errors: list[str]
    valid: bool
    raw: list[str]
    # resolution metadata
    account_id: int | None
    category_state: str  # existing | new | none
    dedupe_key: str | None
    duplicate: bool


class ImportPreviewResponse(APIModel):
    filename: str | None
    columns: list[str]
    rows: list[PreviewRow]
    counts: PreviewCounts


class CommitCounts(APIModel):
    total: int
    created: int
    skipped_duplicates: int
    skipped_invalid: int
    categories_created: int


class RowError(APIModel):
    row_number: int
    errors: list[str]


class ImportCommitResponse(APIModel):
    batch_id: str
    filename: str | None
    counts: CommitCounts
    accounts_touched: list[int]
    errors: list[RowError]
