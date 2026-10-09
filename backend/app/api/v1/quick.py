"""Quick Add and suggestion endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.quick import (
    QuickCaptureRequest,
    QuickCaptureResponse,
    QuickCreateRequest,
    QuickCreateResponse,
)
from app.services.quick_service import QuickAddService
from app.services.transaction_service import serialize_transaction

router = APIRouter(tags=["quick"])


@router.post("/quick/capture", response_model=QuickCaptureResponse)
def quick_capture(
    payload: QuickCaptureRequest,
    session: Session = Depends(get_db),
) -> QuickCaptureResponse:
    """Resolve defaults + suggestions for a Quick Add, without writing."""
    result = QuickAddService(session).resolve_capture(
        type=payload.type,
        description=payload.description,
        amount=payload.amount,
        on=payload.date,
        account_id=payload.account_id,
        category_id=payload.category_id,
    )
    return QuickCaptureResponse(**result)


@router.post("/quick/transactions", response_model=QuickCreateResponse)
def quick_create(
    payload: QuickCreateRequest,
    session: Session = Depends(get_db),
) -> QuickCreateResponse:
    """Create a transaction using Quick Add defaults."""
    result = QuickAddService(session).create(
        type=payload.type,
        amount=payload.amount,
        description=payload.description,
        on=payload.date,
        account_id=payload.account_id,
        category_id=payload.category_id,
        notes=payload.notes,
        reject_duplicate=payload.reject_duplicate,
        check_duplicate=payload.check_duplicate,
    )
    return QuickCreateResponse(
        transaction=serialize_transaction(result["transaction"]),
        duplicates=result["duplicates"],
    )