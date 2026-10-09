"""Supported currencies and their display symbols (pure, no deps).

These three-letter codes are the only currencies Pilote Budget persists;
``SettingsService`` validates the user's choice against ``SUPPORTED_CURRENCIES``.
"""

from __future__ import annotations

SUPPORTED_CURRENCIES: frozenset[str] = frozenset(
    {"USD", "EUR", "GBP", "CAD", "AUD", "NZD", "CHF", "JPY", "INR"}
)

CURRENCY_SYMBOLS: dict[str, str] = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "CAD": "$",
    "AUD": "$",
    "NZD": "$",
    "CHF": "CHF ",
    "JPY": "¥",
    "INR": "₹",
}

FALLBACK_SYMBOL = "¤"


def symbol_for(currency: str | None) -> str:
    """Return the display symbol for a currency (or the fallback glyph)."""
    if not currency:
        return FALLBACK_SYMBOL
    return CURRENCY_SYMBOLS.get(currency.upper(), FALLBACK_SYMBOL)