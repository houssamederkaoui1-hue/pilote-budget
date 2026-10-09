"""Category CRUD plus the default seed set."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.enums import CategoryType
from app.domain.errors import ConflictError, NotFoundError, ValidationError
from app.models.category import Category
from app.models.transaction import Transaction

# Sensible starter set; users are free to edit or replace everything.
DEFAULT_CATEGORIES: list[tuple[str, CategoryType]] = [
    ("Housing", CategoryType.EXPENSE),
    ("Food", CategoryType.EXPENSE),
    ("Transport", CategoryType.EXPENSE),
    ("Shopping", CategoryType.EXPENSE),
    ("Entertainment", CategoryType.EXPENSE),
    ("Health", CategoryType.EXPENSE),
    ("Subscriptions", CategoryType.EXPENSE),
    ("Education", CategoryType.EXPENSE),
    ("Travel", CategoryType.EXPENSE),
    ("Utilities", CategoryType.EXPENSE),
    ("Salary", CategoryType.INCOME),
    ("Freelance", CategoryType.INCOME),
    ("Other", CategoryType.EXPENSE),
    ("Other", CategoryType.INCOME),
]


class CategoryService:
    def __init__(self, session: Session):
        self.session = session

    # -- reads ------------------------------------------------------------

    def list(self, *, include_archived: bool = False, type: str | None = None) -> list[Category]:
        self.ensure_defaults()
        stmt = select(Category)
        if not include_archived:
            stmt = stmt.where(Category.active.is_(True))
        if type:
            stmt = stmt.where(Category.type == self._coerce_type(type))
        return list(self.session.scalars(stmt.order_by(Category.type, Category.name)))

    def get(self, category_id: int) -> Category:
        category = self.session.get(Category, category_id)
        if category is None:
            raise NotFoundError(f"Category {category_id} not found")
        return category

    def ensure_defaults(self) -> None:
        """Seed the default categories the first time categories are read."""
        existing = self.session.scalar(select(func.count()).select_from(Category))
        if existing:
            return
        for name, category_type in DEFAULT_CATEGORIES:
            self.session.add(Category(name=name, type=category_type))
        self.session.flush()

    # -- writes -----------------------------------------------------------

    def create(
        self,
        *,
        name: str,
        type: str | CategoryType,
        parent_id: int | None = None,
        description: str | None = None,
        active: bool = True,
    ) -> Category:
        cleaned_name = self._clean_name(name)
        category_type = self._coerce_type(type)
        self._ensure_unique(cleaned_name, category_type)
        parent = self._resolve_parent(parent_id, category_type)

        category = Category(
            name=cleaned_name,
            type=category_type,
            parent_id=parent.id if parent else None,
            description=(description or "").strip() or None,
            active=active,
        )
        self.session.add(category)
        self.session.flush()
        return category

    def update(self, category_id: int, **fields) -> Category:
        category = self.get(category_id)

        if "name" in fields and fields["name"] is not None:
            cleaned_name = self._clean_name(fields["name"])
            if cleaned_name.lower() != category.name.lower():
                self._ensure_unique(cleaned_name, category.type, exclude_id=category_id)
            category.name = cleaned_name
        if "type" in fields and fields["type"] is not None:
            new_type = self._coerce_type(fields["type"])
            if new_type != category.type:
                self._ensure_unique(category.name, new_type, exclude_id=category_id)
                if self._usage_count(category_id):
                    raise ConflictError(
                        "Cannot change the type of a category that is already in use"
                    )
            category.type = new_type
        if "parent_id" in fields:
            parent = self._resolve_parent(
                fields["parent_id"], category.type, exclude_id=category_id
            )
            category.parent_id = parent.id if parent else None
        if "description" in fields:
            category.description = (fields["description"] or "").strip() or None
        if "active" in fields and fields["active"] is not None:
            category.active = bool(fields["active"])

        self.session.flush()
        return category

    def archive(self, category_id: int, *, active: bool = False) -> Category:
        return self.update(category_id, active=active)

    def delete(self, category_id: int) -> None:
        category = self.get(category_id)
        if self._usage_count(category_id):
            raise ConflictError(
                "Category is used by existing transactions; archive it instead"
            )
        # Children are re-parented to keep the tree intact.
        children = self.session.scalars(
            select(Category).where(Category.parent_id == category_id)
        ).all()
        for child in children:
            child.parent_id = category.parent_id
        self.session.delete(category)
        self.session.flush()

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _clean_name(name: str | None) -> str:
        cleaned = (name or "").strip()
        if not cleaned:
            raise ValidationError("Category name is required")
        if len(cleaned) > 120:
            raise ValidationError("Category name must be 120 characters or fewer")
        return cleaned

    @staticmethod
    def _coerce_type(value: str | CategoryType) -> CategoryType:
        if isinstance(value, CategoryType):
            return value
        try:
            return CategoryType(value)
        except ValueError as exc:
            allowed = ", ".join(member.value for member in CategoryType)
            raise ValidationError(f"Unknown category type '{value}' (allowed: {allowed})") from exc

    def _ensure_unique(
        self, name: str, category_type: CategoryType, exclude_id: int | None = None
    ) -> None:
        stmt = select(func.count()).select_from(Category).where(
            func.lower(Category.name) == name.lower(), Category.type == category_type
        )
        if exclude_id is not None:
            stmt = stmt.where(Category.id != exclude_id)
        if self.session.scalar(stmt):
            raise ConflictError(
                f"A '{category_type.value}' category named '{name}' already exists"
            )

    def _resolve_parent(
        self,
        parent_id: int | None,
        category_type: CategoryType,
        exclude_id: int | None = None,
    ) -> Category | None:
        if parent_id is None:
            return None
        parent = self.session.get(Category, parent_id)
        if parent is None:
            raise ValidationError(f"Parent category {parent_id} not found")
        if exclude_id is not None and parent.id == exclude_id:
            raise ValidationError("A category cannot be its own parent")
        if parent.type != category_type:
            raise ValidationError("Parent category must have the same type")
        # Guard against cycles: walk up from the parent.
        seen = {parent.id}
        cursor = parent.parent_id
        while cursor is not None:
            if cursor in seen or cursor == exclude_id:
                raise ValidationError("Category parent chain forms a cycle")
            seen.add(cursor)
            ancestor = self.session.get(Category, cursor)
            cursor = ancestor.parent_id if ancestor else None
        return parent

    def _usage_count(self, category_id: int) -> int:
        return int(
            self.session.scalar(
                select(func.count())
                .select_from(Transaction)
                .where(Transaction.category_id == category_id)
            )
            or 0
        )
