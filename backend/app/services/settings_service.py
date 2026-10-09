"""Settings service: validation + persistence for user-facing preferences.

Preferences live on the singleton ``Profile`` row either as first-class columns
(currency, month_start_day, timezone) or inside the ``preferences`` JSON blob.
All validation happens here so the API layer stays thin and the rules can be
unit tested without FastAPI.
"""

from __future__ import annotations

import math

from sqlalchemy.orm import Session

from app.domain.errors import NotFoundError, ValidationError
from app.domain.currency import SUPPORTED_CURRENCIES
from app.domain.enums import CategoryType
from app.domain.settings import (
    ALL_DASHBOARD_SECTION_IDS,
    ASSISTANT_VERBOSITIES,
    DEFAULT_ASSISTANT,
    DEFAULT_ASSISTANT_VERBOSITY,
    DEFAULT_DASHBOARD,
    PREFERRED_PERIODS,
)
from app.models.account import Account
from app.models.category import Category
from app.services.profile_service import ProfileService


def _clean_dashboard(incoming: dict | None) -> dict:
    if not isinstance(incoming, dict) or not incoming:
        incoming = DEFAULT_DASHBOARD
    period = incoming.get("period", DEFAULT_DASHBOARD["period"])
    if period not in PREFERRED_PERIODS:
        raise ValidationError(
            f"Unsupported dashboard period '{period}'. "
            f"Allowed: {', '.join(PREFERRED_PERIODS)}."
        )
    sections_in = incoming.get("sections")
    if not isinstance(sections_in, dict):
        sections_in = {}
    sections = {
        section_id: bool(sections_in.get(section_id, DEFAULT_DASHBOARD["sections"][section_id]))
        for section_id in ALL_DASHBOARD_SECTION_IDS
    }
    order_in = incoming.get("order") or []
    if not isinstance(order_in, list):
        raise ValidationError("Dashboard section order must be a list.")
    if len(set(order_in)) != len(order_in):
        raise ValidationError("Dashboard section order contains duplicates.")
    unknown = [sid for sid in order_in if sid not in ALL_DASHBOARD_SECTION_IDS]
    if unknown:
        raise ValidationError(
            "Unknown dashboard section(s): " + ", ".join(sorted(unknown)) + "."
        )
    order = [sid for sid in order_in if sid in ALL_DASHBOARD_SECTION_IDS]
    order += [sid for sid in DEFAULT_DASHBOARD["order"] if sid not in order]
    return {"period": period, "sections": sections, "order": order}


class SettingsService:
    def __init__(self, session: Session):
        self.session = session
        self.profiles = ProfileService(session)

    # -- queries ---------------------------------------------------------------

    def get_settings(self) -> dict:
        profile = self.profiles.get()
        prefs = profile.preferences or {}
        dashboard = _clean_dashboard(prefs.get("dashboard"))
        assistant = {**DEFAULT_ASSISTANT, **(prefs.get("assistant") or {})}
        return {
            "currency": profile.currency,
            "month_start_day": profile.month_start_day,
            "timezone": profile.timezone,
            "minimum_reserve": round(float(prefs.get("minimum_reserve") or 0.0), 2),
            "default_account_id": prefs.get("default_account_id"),
            "default_expense_category_id": prefs.get("default_expense_category_id"),
            "default_income_category_id": prefs.get("default_income_category_id"),
            "dashboard": dashboard,
            "assistant": assistant,
            "updated_at": profile.updated_at,
        }

    # -- commands ---------------------------------------------------------------

    def update_settings(self, updates: dict) -> dict:
        currency = updates.get("currency")
        if currency is not None:
            currency = currency.strip().upper()
            if currency not in SUPPORTED_CURRENCIES:
                raise ValidationError(
                    f"Unsupported currency '{currency}'. "
                    f"Supported: {', '.join(sorted(SUPPORTED_CURRENCIES))}."
                )
        month_start_day = updates.get("month_start_day")
        if month_start_day is not None and not 1 <= int(month_start_day) <= 28:
            raise ValidationError("month_start_day must be between 1 and 28.")

        minimum_reserve = updates.get("minimum_reserve")
        if minimum_reserve is not None:
            if isinstance(minimum_reserve, bool) or not isinstance(minimum_reserve, (int, float)):
                raise ValidationError("minimum_reserve must be a number.")
            if not math.isfinite(float(minimum_reserve)) or float(minimum_reserve) < 0:
                raise ValidationError("minimum_reserve must be a non-negative number.")
            minimum_reserve = round(float(minimum_reserve), 2)

        prefs: dict = {}
        if minimum_reserve is not None:
            prefs["minimum_reserve"] = minimum_reserve
        if "default_account_id" in updates:
            prefs["default_account_id"] = self._require_active_account(
                updates["default_account_id"]
            )
        if "default_expense_category_id" in updates:
            prefs["default_expense_category_id"] = self._require_category(
                updates["default_expense_category_id"], CategoryType.EXPENSE
            )
        if "default_income_category_id" in updates:
            prefs["default_income_category_id"] = self._require_category(
                updates["default_income_category_id"], CategoryType.INCOME
            )
        if "dashboard" in updates:
            prefs["dashboard"] = _clean_dashboard(updates["dashboard"])
        if "assistant" in updates:
            assistant = updates["assistant"]
            if not isinstance(assistant, dict):
                raise ValidationError("Assistant preferences must be an object.")
            verbosity = assistant.get("verbosity", DEFAULT_ASSISTANT_VERBOSITY)
            if verbosity not in ASSISTANT_VERBOSITIES:
                raise ValidationError(
                    f"Unsupported assistant verbosity '{verbosity}'. "
                    f"Allowed: {', '.join(ASSISTANT_VERBOSITIES)}."
                )
            prefs["assistant"] = {"verbosity": verbosity}

        values: dict = {}
        if currency is not None:
            values["currency"] = currency
        if month_start_day is not None:
            values["month_start_day"] = int(month_start_day)
        if updates.get("timezone") is not None:
            values["timezone"] = updates["timezone"].strip() or "UTC"

        self.profiles.update(**values, preferences=prefs if prefs else None)
        return self.get_settings()

    # -- helpers ---------------------------------------------------------------

    def _require_active_account(self, account_id: int | None) -> int | None:
        if account_id is None:
            return None
        account = self.session.get(Account, account_id)
        if account is None:
            raise NotFoundError(f"Account {account_id} does not exist.")
        if not account.active:
            raise ValidationError(f"Account '{account.name}' is archived.")
        return int(account.id)

    def _require_category(self, category_id: int | None, kind: CategoryType) -> int | None:
        if category_id is None:
            return None
        category = self.session.get(Category, category_id)
        if category is None:
            raise NotFoundError(f"Category {category_id} does not exist.")
        if not category.active:
            raise ValidationError(f"Category '{category.name}' is archived.")
        if category.type is not kind:
            raise ValidationError(
                f"Category '{category.name}' is for "
                f"'{category.type.value}' but a '{kind.value}' category is required."
            )
        return int(category.id)