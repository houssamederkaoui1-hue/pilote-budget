"""Financial overview schema (assets / liabilities / net worth)."""

from __future__ import annotations

from app.schemas.base import APIModel


class OverviewResponse(APIModel):
    total_assets: float
    total_liabilities: float
    net_worth: float
    account_assets: float
    account_liabilities: float
    debt_liabilities: float