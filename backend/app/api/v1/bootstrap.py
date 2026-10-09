"""Public bootstrap endpoint (no auth): tells the SPA whether a token is needed."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.config import Settings, get_settings

router = APIRouter(tags=["public"])


@router.get("/config")
def public_config(request: Request) -> dict:
    """Non-sensitive, unauthenticated app metadata for the SPA bootstrap.

    Marks ``auth_required`` so the web app can show its token screen before
    any data is loaded. Never exposes the token itself.
    """
    settings: Settings = getattr(request.app.state, "settings", None) or get_settings()
    return {
        "app": settings.app_name,
        "version": settings.version,
        "environment": settings.environment,
        "api_prefix": settings.api_prefix,
        "auth_required": settings.auth_enabled,
    }