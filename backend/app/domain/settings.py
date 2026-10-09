"""Settings vocabulary shared by the service, API and validation.

Pure data (no SQLAlchemy/FastAPI) so it can be unit tested in isolation and
reused by the frontend contract via the API schemas.
"""

from __future__ import annotations

# --- preferred dashboard period ---------------------------------------------

PREFERRED_PERIODS: tuple[str, ...] = ("current", "last_three")

# --- dashboard sections ------------------------------------------------------

# Ordered, stable ids for every major dashboard block. The settings payload
# stores per-section visibility plus an order (subset + reorder) so the UI can
# personalize without becoming a drag-and-drop builder.
DASHBOARD_SECTIONS: tuple[dict[str, str], ...] = (
    {"id": "stats", "label": "Overview cards"},
    {"id": "cash_flow", "label": "Cash flow"},
    {"id": "category_spending", "label": "Spending by category"},
    {"id": "net_worth", "label": "Net worth"},
    {"id": "budget_vs_actual", "label": "Budget vs actual"},
    {"id": "safe_to_spend", "label": "Safe-to-Spend"},
    {"id": "forecast", "label": "Forecast"},
    {"id": "financial_health", "label": "Financial health"},
    {"id": "insights", "label": "Financial insights"},
    {"id": "goals", "label": "Goals"},
    {"id": "upcoming_bills", "label": "Upcoming recurring expenses"},
    {"id": "debts", "label": "Debt summary"},
)

ALL_DASHBOARD_SECTION_IDS = frozenset(item["id"] for item in DASHBOARD_SECTIONS)

# --- assistant preferences ---------------------------------------------------

ASSISTANT_VERBOSITIES: tuple[str, ...] = ("concise", "standard")
DEFAULT_ASSISTANT_VERBOSITY = "standard"

# --- defaults ----------------------------------------------------------------

DEFAULT_DASHBOARD = {
    "period": PREFERRED_PERIODS[0],
    "sections": {item["id"]: True for item in DASHBOARD_SECTIONS},
    "order": [item["id"] for item in DASHBOARD_SECTIONS],
}

DEFAULT_ASSISTANT = {"verbosity": DEFAULT_ASSISTANT_VERBOSITY}