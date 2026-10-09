"""Settings and on-boarding endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.settings import (
    OnboardingResponse,
    OnboardingUpdate,
    SettingsResponse,
    SettingsUpdate,
)
from app.services.onboarding_service import OnboardingService
from app.services.settings_service import SettingsService

router = APIRouter(tags=["settings"])


@router.get("/settings", response_model=SettingsResponse)
def get_settings(session: Session = Depends(get_db)) -> SettingsResponse:
    return SettingsResponse(**SettingsService(session).get_settings())


@router.put("/settings", response_model=SettingsResponse)
def update_settings(
    payload: SettingsUpdate,
    session: Session = Depends(get_db),
) -> SettingsResponse:
    return SettingsResponse(
        **SettingsService(session).update_settings(payload.model_dump(exclude_unset=True))
    )


@router.get("/settings/onboarding", response_model=OnboardingResponse)
def get_onboarding(session: Session = Depends(get_db)) -> OnboardingResponse:
    return OnboardingResponse(**OnboardingService(session).get_state())


@router.put("/settings/onboarding", response_model=OnboardingResponse)
def update_onboarding(
    payload: OnboardingUpdate,
    session: Session = Depends(get_db),
) -> OnboardingResponse:
    return OnboardingResponse(**OnboardingService(session).set_skipped(payload.skipped))