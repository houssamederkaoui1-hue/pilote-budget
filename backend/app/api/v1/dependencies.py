"""Shared FastAPI dependencies."""

from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings, get_settings

# Static helper: HTTPBearer(auto_error=False) keeps 401 responses uniform.
_bearer = HTTPBearer(auto_error=False)


def _settings_for(request: Request) -> Settings:
    """Prefer the settings the app was built with (testable, DRY)."""
    return getattr(request.app.state, "settings", None) or get_settings()


def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    """Gate a route behind the shared ``PILOTE_ACCESS_TOKEN``.

    When no token is configured (local development) the dependency is a no-op.
    When it is set, requests without a matching ``Authorization: Bearer``
    header get a 401. Comparison is constant-time.
    """
    settings = _settings_for(request)
    if not settings.auth_enabled:
        return
    if credentials is None or not secrets.compare_digest(
        credentials.credentials, settings.access_token or ""
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )