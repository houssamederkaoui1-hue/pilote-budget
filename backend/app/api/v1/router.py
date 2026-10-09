"""Versioned API router.

All feature routers are registered here so the surface stays in one place:
``/api/v1/...``. The health check and the public ``/config`` bootstrap stay
unauthenticated (Render's health probe cannot send a token); every other
router is protected by ``require_auth`` when ``PILOTE_ACCESS_TOKEN`` is set.
"""

from fastapi import APIRouter, Depends

from app.api.v1 import (
    accounts,
    analytics,
    backup,
    bootstrap,
    budgets,
    categories,
    debts,
    financial_assistant,
    goals,
    health,
    imports,
    overview,
    profile,
    quick,
    recurring,
    settings,
    transactions,
)
from app.api.v1.dependencies import require_auth

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(bootstrap.router)

_protected_routers = [
    profile,
    settings,
    accounts,
    categories,
    transactions,
    imports,
    budgets,
    goals,
    recurring,
    debts,
    overview,
    analytics,
    financial_assistant,
    quick,
    backup,
]
for _router in _protected_routers:
    api_router.include_router(_router.router, dependencies=[Depends(require_auth)])