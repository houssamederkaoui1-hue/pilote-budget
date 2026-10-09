"""Health endpoint."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.health import HealthResponse
from app.services.health_service import HealthService

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health(
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HealthResponse:
    result = HealthService(session, settings).check()
    return HealthResponse(
        status=result["status"],
        app=result["app"],
        version=result["version"],
        environment=result["environment"],
        database=result["database"],
        time=datetime.now(timezone.utc),
    )
