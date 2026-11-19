"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.v1.router import api_router
from app.config import Settings, get_settings
from app.db.schema import ensure_schema
from app.domain.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    ValidationError,
)

# Expected domain errors -> HTTP status codes.
DOMAIN_ERROR_STATUS: list[tuple[type[DomainError], int]] = [
    (ValidationError, 400),
    (NotFoundError, 404),
    (ConflictError, 409),
]

logger = logging.getLogger("pilote")

_UNEXPECTED = "Something went wrong on our side. Nothing was saved."
_DB_BUSY = "The local database is busy right now. Please try again."
_DB_CONFLICT = "That record conflicts with something else. Please refresh and try again."


def _configure_logging() -> None:
    if logging.getLogger().handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    _configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        ensure_schema(resolved)
        yield

    app = FastAPI(
        title=resolved.app_name,
        version=resolved.version,
        description="Local-first personal finance API.",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url="/openapi.json" if resolved.debug else None,
    )
    app.state.settings = resolved

    for error_type, status_code in DOMAIN_ERROR_STATUS:
        @app.exception_handler(error_type)
        async def _domain_error_handler(
            request: Request, exc: DomainError, _status: int = status_code
        ) -> JSONResponse:
            return JSONResponse(status_code=_status, content={"detail": exc.message})

    @app.exception_handler(DomainError)
    async def _bare_domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": exc.message})

    @app.exception_handler(RequestValidationError)
    async def _request_validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        parts = []
        for error in exc.errors():
            loc = error.get("loc", ())
            field = ".".join(str(part) for part in loc[1:] if part not in ("body", "query", "path"))
            message = str(error.get("msg", "invalid value"))
            if field:
                parts.append(f"{field}: {message}")
            else:
                parts.append(message)
        detail = " · ".join(parts) or "Invalid request"
        return JSONResponse(status_code=422, content={"detail": detail})

    @app.exception_handler(IntegrityError)
    async def _integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": _DB_CONFLICT})

    @app.exception_handler(OperationalError)
    async def _operational_error_handler(request: Request, exc: OperationalError) -> JSONResponse:
        message = str(exc).lower()
        if "locked" in message or "busy" in message:
            return JSONResponse(status_code=503, content={"detail": _DB_BUSY})
        return JSONResponse(status_code=500, content={"detail": _UNEXPECTED})

    @app.exception_handler(Exception)
    async def _unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        # Log the class and traceback only — never request bodies, query
        # strings or financial data, which stay on the wire.
        logger.exception("Unhandled exception (%s)", type(exc).__name__)
        return JSONResponse(status_code=500, content={"detail": _UNEXPECTED})

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
    app.include_router(api_router, prefix=resolved.api_prefix)

    @app.get("/", tags=["system"])
    def root() -> dict:
        return {
            "app": resolved.app_name,
            "version": resolved.version,
            "environment": resolved.environment,
            "openapi": app.openapi_url,
            "api": resolved.api_prefix,
        }

    return app


# ASGI entry point for `uvicorn app.main:app`.
app = create_app()
