"""User profile / settings service."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.periods import clamp_month_start_day
from app.models.profile import Profile


class ProfileService:
    def __init__(self, session: Session):
        self.session = session

    def get(self) -> Profile:
        """Return the singleton profile, creating it with defaults if absent."""
        profile = self.session.get(Profile, Profile.DEFAULT_ID)
        if profile is None:
            profile = Profile(id=Profile.DEFAULT_ID)
            self.session.add(profile)
            self.session.flush()
        return profile

    def list_all(self) -> list[Profile]:
        return list(self.session.scalars(select(Profile)))

    def update(
        self,
        *,
        currency: str | None = None,
        month_start_day: int | None = None,
        timezone: str | None = None,
        preferences: dict | None = None,
    ) -> Profile:
        profile = self.get()
        if currency is not None:
            profile.currency = currency.upper()
        if month_start_day is not None:
            profile.month_start_day = clamp_month_start_day(month_start_day)
        if timezone is not None:
            profile.timezone = timezone
        if preferences is not None:
            profile.preferences = {**profile.preferences, **preferences}
        self.session.flush()
        return profile
