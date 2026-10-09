"""Framework-independent domain errors.

The API layer maps these to HTTP status codes (see ``app.main``); services
raise them for any business rule violation so they can also be unit tested
without FastAPI.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for expected, user-facing errors."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ValidationError(DomainError):
    """Input that breaks a business rule (400)."""


class NotFoundError(DomainError):
    """Referenced entity does not exist (404)."""


class ConflictError(DomainError):
    """State conflict: duplicates, records in use, unsafe deletion (409)."""
