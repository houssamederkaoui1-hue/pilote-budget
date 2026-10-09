"""Settings, on-boarding and backup API schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.base import APIModel
from app.schemas.profile import ProfileResponse


# --- settings ----------------------------------------------------------------


class DashboardPreferences(APIModel):
    period: str = "current"
    sections: dict[str, bool] = {}
    order: list[str] = []


class AssistantPreferences(APIModel):
    verbosity: str = "standard"


class SettingsResponse(APIModel):
    """Full settings surface currently in effect (server authoritative)."""

    currency: str
    month_start_day: int
    timezone: str
    minimum_reserve: float
    default_account_id: int | None
    default_expense_category_id: int | None
    default_income_category_id: int | None
    dashboard: DashboardPreferences
    assistant: AssistantPreferences
    updated_at: datetime


class SettingsUpdate(APIModel):
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    month_start_day: int | None = Field(default=None, ge=1, le=28)
    timezone: str | None = None
    minimum_reserve: float | None = None
    default_account_id: int | None = None
    default_expense_category_id: int | None = None
    default_income_category_id: int | None = None
    dashboard: DashboardPreferences | None = None
    assistant: AssistantPreferences | None = None


# --- on-boarding -------------------------------------------------------------


class OnboardingStep(APIModel):
    id: str
    label: str
    complete: bool
    optional: bool = False


class OnboardingResponse(APIModel):
    completed: bool
    skipped: bool
    steps: list[OnboardingStep]
    profile: ProfileResponse


class OnboardingUpdate(APIModel):
    """Currently only supports explicitly skipping the wizard."""

    skipped: bool = True


# --- backup / restore --------------------------------------------------------


class BackupRowCount(APIModel):
    table: str
    rows: int


class BackupExportResponse(APIModel):
    format: str
    version: int
    exported_at: str
    counts: list[BackupRowCount]
    data: dict


class BackupValidateResponse(APIModel):
    valid: bool
    format: str
    version: int
    counts: list[BackupRowCount]
    message: str


class BackupRestoreRequest(APIModel):
    payload: dict
    confirmed: bool = False