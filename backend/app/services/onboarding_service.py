"""Onboarding service: derive wizard progress from persisted state.

Progress is not stored as a flag — it is computed from the actual data, so
restoring a backup or adding data through any screen advances the wizard
naturally. The only explicit preference is ``skipped``.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.budget import Budget
from app.models.category import Category
from app.models.goal import Goal
from app.services.profile_service import ProfileService

ONBOARDING_PREFERENCE = "onboarding"


def _count(session: Session, model) -> int:
    return session.execute(select(model.id).limit(1)).first() is not None


class OnboardingService:
    STEPS: tuple[tuple[str, str, bool], ...] = (
        ("account", "Set up your first account", False),
        ("categories", "Pick your spending categories", False),
        ("budget", "Plan your first budget", True),
        ("goals", "Create your first goal", True),
    )

    def __init__(self, session: Session):
        self.session = session

    def get_state(self) -> dict:
        profile = ProfileService(self.session).get()
        prefs = profile.preferences or {}
        onboarding = prefs.get(ONBOARDING_PREFERENCE) or {}

        account_done = _count(self.session, Account)
        category_done = _count(self.session, Category)
        budget_done = _count(self.session, Budget)
        goal_done = _count(self.session, Goal)
        done = {
            "account": account_done,
            "categories": category_done,
            "budget": budget_done,
            "goals": goal_done,
        }
        self.session.commit()
        return {
            "completed": account_done and category_done,
            "skipped": bool(onboarding.get("skipped") or onboarding.get("skipped") is True),
            "steps": [
                {
                    "id": step_id,
                    "label": label,
                    "complete": bool(done[step_id]),
                    "optional": optional,
                }
                for step_id, label, optional in self.STEPS
            ],
            "profile": profile,
        }

    def set_skipped(self, skipped: bool = True) -> dict:
        ProfileService(self.session).update(
            preferences={ONBOARDING_PREFERENCE: {"skipped": bool(skipped)}}
        )
        self.session.commit()
        return self.get_state()