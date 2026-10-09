"""Category endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.base import MessageResponse
from app.schemas.category import CategoryCreate, CategoryResponse, CategoryUpdate
from app.services.category_service import CategoryService

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryResponse])
def list_categories(
    include_archived: bool = Query(False),
    type: str | None = Query(None),
    session: Session = Depends(get_db),
) -> list[CategoryResponse]:
    categories = CategoryService(session).list(include_archived=include_archived, type=type)
    return [CategoryResponse.model_validate(category) for category in categories]


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CategoryCreate, session: Session = Depends(get_db)
) -> CategoryResponse:
    category = CategoryService(session).create(**payload.model_dump())
    return CategoryResponse.model_validate(category)


@router.get("/{category_id}", response_model=CategoryResponse)
def get_category(category_id: int, session: Session = Depends(get_db)) -> CategoryResponse:
    category = CategoryService(session).get(category_id)
    return CategoryResponse.model_validate(category)


@router.patch("/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: int,
    payload: CategoryUpdate,
    session: Session = Depends(get_db),
) -> CategoryResponse:
    fields = payload.model_dump(exclude_unset=True)
    category = CategoryService(session).update(category_id, **fields)
    return CategoryResponse.model_validate(category)


@router.delete("/{category_id}", response_model=MessageResponse)
def delete_category(category_id: int, session: Session = Depends(get_db)) -> MessageResponse:
    CategoryService(session).delete(category_id)
    return MessageResponse(message="Category deleted")


@router.post("/{category_id}/archive", response_model=CategoryResponse)
def archive_category(category_id: int, session: Session = Depends(get_db)) -> CategoryResponse:
    category = CategoryService(session).archive(category_id, active=False)
    return CategoryResponse.model_validate(category)


@router.post("/{category_id}/activate", response_model=CategoryResponse)
def activate_category(category_id: int, session: Session = Depends(get_db)) -> CategoryResponse:
    category = CategoryService(session).archive(category_id, active=True)
    return CategoryResponse.model_validate(category)
