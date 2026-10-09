"""Profile (user settings) endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.profile import ProfileResponse
from app.services.profile_service import ProfileService

router = APIRouter(tags=["profile"])


@router.get("/profile", response_model=ProfileResponse)
def get_profile(session: Session = Depends(get_db)) -> ProfileResponse:
    """Return the singleton user profile (creates defaults on first call)."""
    return ProfileService(session).get()
