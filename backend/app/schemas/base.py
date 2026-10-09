"""Shared Pydantic schema primitives."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class APIModel(BaseModel):
    """Base for every API schema: reads directly from ORM objects."""

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(APIModel):
    message: str
