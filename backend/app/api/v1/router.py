"""Register the local feature routes under /api/v1."""

from fastapi import APIRouter

from app.api.v1 import (
    accounts,
    analytics,
    backup,
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

api_router = APIRouter()
for feature in (
    health,
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
):
    api_router.include_router(feature.router)
