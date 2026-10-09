"""CSV inspection, flexible column mapping and row normalization.

Everything in this module is pure (no database, no FastAPI) so the mapping
layer can be unit tested directly and reused by preview, validation and the
actual import. No bank format is assumed: the caller provides an explicit
:class:`ImportMapping`, which inspection only *suggests*.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime

# ---------------------------------------------------------------------------
# Date handling
# ---------------------------------------------------------------------------

# Ordered by preference (ISO first, then European day-first, then US).
DATE_FORMAT_CANDIDATES: list[str] = [
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d.%m.%Y",
    "%Y/%m/%d",
    "%d-%m-%Y",
    "%m-%d-%Y",
    "%Y%m%d",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%d/%m/%y",
    "%m/%d/%y",
    "%Y-%m-%d %H:%M:%S",
    "%d/%m/%Y %H:%M",
]


def parse_date(raw: str | None, fmt: str = "auto") -> date | None:
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None

    candidates = DATE_FORMAT_CANDIDATES if fmt in ("", "auto", None) else [fmt]
    for candidate in candidates:
        parsed = _strptime(candidate, value)
        if parsed is not None:
            return parsed
    # Retry with the time part stripped ("2026-10-01 09:15" -> "2026-10-01").
    if " " in value:
        head = value.split(" ")[0]
        if head != value:
            for candidate in candidates:
                parsed = _strptime(candidate, head)
                if parsed is not None:
                    return parsed
    return None


def _strptime(fmt: str, value: str) -> date | None:
    try:
        return datetime.strptime(value, fmt).date()
    except ValueError:
        return None


def matching_date_formats(sample_values: list[str]) -> list[str]:
    """Candidate formats that parse every non-empty sample value."""
    samples = [str(v).strip() for v in sample_values if str(v).strip()]
    if not samples:
        return []
    matches = []
    for fmt in DATE_FORMAT_CANDIDATES:
        if all(parse_date(sample, fmt) is not None for sample in samples):
            matches.append(fmt)
    return matches


# ---------------------------------------------------------------------------
# Amount handling
# ---------------------------------------------------------------------------

_CURRENCY_JUNK = re.compile(r"[^\d.,+\-]")


def parse_amount(raw: str | None, decimal_separator: str = "auto") -> float | None:
    """Parse human/bank formatted amounts ("1.234,56", "(12.30)", "$1,234").

    ``decimal_separator`` may be ``"."``, ``","`` or ``"auto"`` (heuristic:
    when both separators appear the rightmost one is the decimal separator).
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None

    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]

    text = _CURRENCY_JUNK.sub("", text)
    if not text or text in {"+", "-", ".", ","}:
        return None
    if text.startswith("-"):
        negative = not negative
        text = text[1:]
    elif text.startswith("+"):
        text = text[1:]

    has_comma = "," in text
    has_dot = "." in text

    if decimal_separator == ".":
        text = text.replace(",", "")
    elif decimal_separator == ",":
        text = text.replace(".", "").replace(",", ".")
    else:
        if has_comma and has_dot:
            # Rightmost separator is the decimal one.
            if text.rfind(",") > text.rfind("."):
                text = text.replace(".", "").replace(",", ".")
            else:
                text = text.replace(",", "")
        elif has_comma:
            text = _resolve_single_separator(text, ",")
        elif has_dot:
            text = _resolve_single_separator(text, ".")

    if not text or not re.fullmatch(r"\d*\.?\d*", text):
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    if negative:
        value = -value
    return value


def _resolve_single_separator(text: str, separator: str) -> str:
    """Interpret a string that only uses one kind of separator.

    - multiple separators with a 3-digit tail -> thousands grouping
      ("1,234,567" -> 1234567);
    - multiple separators with a 1-2 digit tail -> last one is decimal
      ("1,500,50" -> 1500.50, ",1500,50" -> 1500.50);
    - one separator with a 3-digit tail and a small head -> thousands
      ("1,234" -> 1234, but "0.123" stays 0.123);
    - otherwise -> decimal ("12.34" -> 12.34).
    """
    parts = text.split(separator)
    if len(parts) == 1:
        return text
    last = parts[-1]
    if len(parts) > 2:
        if len(last) == 3:
            return "".join(parts)
        if 1 <= len(last) <= 2:
            return f"{''.join(part for part in parts[:-1])}.{last}"
        return text.replace(separator, ".")
    if len(last) == 3 and 1 <= len(parts[0]) <= 3 and parts[0] != "0":
        return "".join(parts)
    return f"{parts[0]}.{last}"


# ---------------------------------------------------------------------------
# File reading / inspection
# ---------------------------------------------------------------------------

ENCODINGS = ("utf-8-sig", "utf-8", "latin-1", "cp1252")


def decode_csv(data: bytes | str, encoding: str = "auto") -> tuple[str, str]:
    """Decode file bytes, returning ``(text, encoding_used)``."""
    if isinstance(data, str):
        return data, "utf-8"
    if encoding and encoding != "auto":
        return data.decode(encoding), encoding
    for candidate in ENCODINGS:
        try:
            return data.decode(candidate), candidate
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace"), "latin-1"


def sniff_delimiter(text: str) -> str:
    sample = text[:8192]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        # Fall back to whichever delimiter appears most often in the header line.
        header = sample.splitlines()[0] if sample else ""
        return max(",;\t|", key=lambda candidate: header.count(candidate))


def read_csv(text: str, delimiter: str | None = None) -> tuple[list[str], list[list[str]]]:
    """Return ``(header, rows)`` skipping blank lines; empty header -> [] ."""
    if not text.strip():
        return [], []
    delimiter = delimiter or sniff_delimiter(text)
    try:
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        rows = [row for row in reader if any(cell.strip() for cell in row)]
    except csv.Error as exc:
        raise MappingError(f"Could not read the CSV file: {exc}") from exc
    if not rows:
        return [], []
    header = [cell.strip() for cell in rows[0]]
    body = [row for row in rows[1:]]
    return header, body


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------

# Checked in this order; the first column claim wins.
FIELD_HINTS: dict[str, list[str]] = {
    "date": ["date", "datum", "booking", "buchung", "valuta", "transaction date", "dated"],
    "debit": [
        "debit", "withdrawal", "withdrawals", "paid out", "charge", "debet",
        "uitvoer", "lastschrift", "ausgabe", "expense", "paid",
    ],
    "credit": [
        "credit", "deposit", "deposits", "paid in", "bijgeschreven", "gutschrift",
        "income", "received", "einnahme",
    ],
    "category": ["category", "kategorie", "categorie", "tag", "budget"],
    "account": ["account", "konto", "compte", "iban", "card", "rekening"],
    "reference": [
        "reference", "reference number", "ref", "transaction id", "transaktionsid",
        "primär-nr", "primarnr", "id", "nr", "number",
    ],
    "description": [
        "description", "details", "detail", "memo", "narrative", "payee",
        "libelle", "label", "verwendungszweck", "merchant", "name", "text",
    ],
    "amount": ["amount", "betrag", "montant", "value", "sum", "total", "summe"],
}

MAPPABLE_FIELDS = (
    "date",
    "description",
    "amount",
    "debit",
    "credit",
    "category",
    "account",
    "reference",
)


def _normalize(header: str) -> str:
    text = unicodedata.normalize("NFKD", str(header))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().lower()


def suggest_mapping(header: list[str]) -> dict[str, dict | None]:
    """Heuristic column suggestions for every mappable field."""
    normalized = [_normalize(cell) for cell in header]
    claimed: set[int] = set()
    suggestions: dict[str, dict | None] = {name: None for name in MAPPABLE_FIELDS}

    for field_name in ("date", "debit", "credit", "category", "account", "reference", "description", "amount"):
        hints = FIELD_HINTS[field_name]
        for level in range(3):  # 0: exact, 1: prefix, 2: contains
            for index, cell in enumerate(normalized):
                if index in claimed or not cell:
                    continue
                if level == 0 and cell in hints:
                    match = True
                elif level == 1 and any(cell.startswith(hint) for hint in hints):
                    match = True
                elif level == 2 and any(hint in cell for hint in hints):
                    match = True
                else:
                    match = False
                if match:
                    claimed.add(index)
                    suggestions[field_name] = {"column": index}
                    break
            if suggestions[field_name]:
                break

    # A dedicated amount column is only suggested when no debit/credit split
    # was found, so both conventions stay unambiguous.
    if suggestions["debit"] or suggestions["credit"]:
        suggestions["amount"] = None
    return suggestions


# ---------------------------------------------------------------------------
# Normalized rows
# ---------------------------------------------------------------------------

AMOUNT_MODES = ("auto", "income", "expense", "flip")
POSITIVE_IS = ("income", "expense")


@dataclass
class FieldMapping:
    column: int | None = None
    format: str | None = None


@dataclass
class ImportOptions:
    encoding: str = "auto"
    decimal_separator: str = "auto"  # "." | "," | "auto"
    amount_mode: str = "auto"  # auto | income | expense | flip
    positive_is: str = "income"  # income | expense (meaning of a positive amount)
    default_account_id: int | None = None
    default_category_id: int | None = None
    filename: str | None = None


@dataclass
class ImportMapping:
    date: FieldMapping = field(default_factory=FieldMapping)
    description: FieldMapping = field(default_factory=FieldMapping)
    amount: FieldMapping = field(default_factory=FieldMapping)
    debit: FieldMapping = field(default_factory=FieldMapping)
    credit: FieldMapping = field(default_factory=FieldMapping)
    category: FieldMapping = field(default_factory=FieldMapping)
    account: FieldMapping = field(default_factory=FieldMapping)
    reference: FieldMapping = field(default_factory=FieldMapping)
    options: ImportOptions = field(default_factory=ImportOptions)


def mapping_from_payload(payload: dict) -> ImportMapping:
    """Build an :class:`ImportMapping` from an API payload, validating enums."""

    def to_field(raw) -> FieldMapping:
        if raw is None:
            return FieldMapping()
        if isinstance(raw, int):
            return FieldMapping(column=raw)
        if not isinstance(raw, dict) or raw.get("column") is None:
            return FieldMapping()
        return FieldMapping(column=int(raw["column"]), format=raw.get("format"))

    options_raw = payload.get("options") or {}
    options = ImportOptions(
        encoding=options_raw.get("encoding") or "auto",
        decimal_separator=options_raw.get("decimal_separator") or "auto",
        amount_mode=options_raw.get("amount_mode") or "auto",
        positive_is=options_raw.get("positive_is") or "income",
        default_account_id=options_raw.get("default_account_id"),
        default_category_id=options_raw.get("default_category_id"),
        filename=options_raw.get("filename"),
    )
    if options.decimal_separator not in ("auto", ".", ","):
        raise ValueError("decimal_separator must be '.', ',' or 'auto'")
    if options.amount_mode not in AMOUNT_MODES:
        raise ValueError(f"amount_mode must be one of {', '.join(AMOUNT_MODES)}")
    if options.positive_is not in POSITIVE_IS:
        raise ValueError(f"positive_is must be one of {', '.join(POSITIVE_IS)}")

    fields_raw = payload.get("fields") or payload
    unknown = set(fields_raw) - set(MAPPABLE_FIELDS) - {"options"}
    if unknown:
        raise ValueError(
            f"Unknown mapping fields: {', '.join(sorted(str(key) for key in unknown))}"
        )
    return ImportMapping(
        date=to_field(fields_raw.get("date")),
        description=to_field(fields_raw.get("description")),
        amount=to_field(fields_raw.get("amount")),
        debit=to_field(fields_raw.get("debit")),
        credit=to_field(fields_raw.get("credit")),
        category=to_field(fields_raw.get("category")),
        account=to_field(fields_raw.get("account")),
        reference=to_field(fields_raw.get("reference")),
        options=options,
    )


@dataclass
class ParsedRow:
    row_number: int
    date: date | None = None
    description: str = ""
    amount: float | None = None  # positive magnitude
    type: str = ""  # income | expense
    category_name: str | None = None
    account_name: str | None = None
    reference: str | None = None
    errors: list[str] = field(default_factory=list)
    raw: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict:
        return {
            "row_number": self.row_number,
            "date": self.date.isoformat() if self.date else None,
            "description": self.description,
            "amount": self.amount,
            "type": self.type,
            "category_name": self.category_name,
            "account_name": self.account_name,
            "reference": self.reference,
            "errors": list(self.errors),
            "valid": self.valid,
            "raw": list(self.raw),
        }


class MappingError(ValueError):
    """The mapping itself is unusable (missing/invalid column references)."""


def parse_rows(
    header: list[str], rows: list[list[str]], mapping: ImportMapping
) -> list[ParsedRow]:
    """Validate the mapping, then normalize and validate every row."""
    column_count = len(header)
    for field_name in MAPPABLE_FIELDS:
        column = getattr(mapping, field_name).column
        if column is not None and (column < 0 or column >= column_count):
            raise MappingError(
                f"Column {column} for '{field_name}' is out of range "
                f"(file has {column_count} columns)"
            )
    if mapping.date.column is None:
        raise MappingError("A date column must be mapped")
    if mapping.amount.column is None and (
        mapping.debit.column is None and mapping.credit.column is None
    ):
        raise MappingError("Map an amount column, or debit and/or credit columns")

    options = mapping.options
    parsed: list[ParsedRow] = []
    for offset, raw_row in enumerate(rows):
        row_number = offset + 2  # 1-based, header is row 1
        row = ParsedRow(row_number=row_number, raw=list(raw_row))

        def cell(field_name: str) -> str:
            column = getattr(mapping, field_name).column
            if column is None or column >= len(raw_row):
                return ""
            return raw_row[column].strip()

        raw_date = cell("date")
        row.date = parse_date(raw_date, mapping.date.format or "auto")
        if row.date is None:
            row.errors.append(
                f"Invalid date: {raw_date!r}" if raw_date else "Date is missing"
            )

        row.description = cell("description")[:255]
        signed = _signed_amount(cell, mapping, options.decimal_separator)
        row.category_name = cell("category") or None
        row.account_name = cell("account") or None
        row.reference = cell("reference") or None

        if signed is None:
            row.errors.append("Amount is missing or not a number")
        else:
            _apply_direction(row, signed, options)

        if not row.description and not row.errors:
            # Descriptions are optional; keep an obvious placeholder instead
            # of an empty cell in previews.
            row.description = ""
        parsed.append(row)
    return parsed


def _signed_amount(cell, mapping: ImportMapping, decimal_separator: str) -> float | None:
    if mapping.amount.column is not None:
        return parse_amount(cell("amount"), decimal_separator)
    credit = 0.0
    debit = 0.0
    has_value = False
    if mapping.credit.column is not None:
        parsed = parse_amount(cell("credit"), decimal_separator)
        if parsed is not None:
            credit = abs(parsed)
            has_value = True
    if mapping.debit.column is not None:
        parsed = parse_amount(cell("debit"), decimal_separator)
        if parsed is not None:
            debit = abs(parsed)
            has_value = True
    if not has_value:
        return None
    return credit - debit


def _apply_direction(row: ParsedRow, signed: float, options: ImportOptions) -> None:
    if options.amount_mode == "income":
        row.type = "income"
        row.amount = round(abs(signed), 2)
    elif options.amount_mode == "expense":
        row.type = "expense"
        row.amount = round(abs(signed), 2)
    else:
        if options.amount_mode == "flip":
            signed = -signed
        if round(signed, 2) == 0:
            row.errors.append("Amount is zero")
            return
        positive_means_income = options.positive_is == "income"
        row.type = "income" if (signed > 0) == positive_means_income else "expense"
        row.amount = round(abs(signed), 2)
    if row.amount == 0:
        row.errors.append("Amount is zero")


# ---------------------------------------------------------------------------
# Inspection (first step of the import workflow)
# ---------------------------------------------------------------------------

def inspect_csv(
    data: bytes | str,
    *,
    filename: str | None = None,
    encoding: str = "auto",
    sample_limit: int = 8,
) -> dict:
    """Read a CSV and describe it: columns, samples, suggested mapping."""
    text, used_encoding = decode_csv(data, encoding)
    delimiter = sniff_delimiter(text)
    header, rows = read_csv(text, delimiter)

    if not header:
        raise MappingError("The file is empty or has no header row")

    suggestions = suggest_mapping(header)
    date_column = (suggestions.get("date") or {}).get("column")
    date_formats: list[str] = []
    if date_column is not None:
        samples = [
            row[date_column] for row in rows[:20] if date_column < len(row)
        ]
        date_formats = matching_date_formats(samples)
        if date_formats:
            suggestions["date"] = {"column": date_column, "format": date_formats[0]}

    return {
        "filename": filename,
        "encoding": used_encoding,
        "delimiter": delimiter,
        "columns": header,
        "sample_rows": [
            list(row) for row in rows[:sample_limit]
        ],
        "row_count": len(rows),
        "suggestions": suggestions,
        "date_formats": date_formats,
        "date_format_candidates": DATE_FORMAT_CANDIDATES,
    }
