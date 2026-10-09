"""Income/expense categories with optional hierarchy."""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.db.types import string_enum
from app.domain.enums import CategoryType


class Category(Base, TimestampMixin):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[CategoryType] = mapped_column(string_enum(CategoryType), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    parent: Mapped[Category | None] = relationship(
        "Category", remote_side=lambda: Category.id, back_populates="children"
    )
    # No delete-orphan cascade: the service re-parents children explicitly
    # before deleting a category, so disassociation must not delete rows.
    children: Mapped[list[Category]] = relationship(
        "Category", back_populates="parent"
    )
