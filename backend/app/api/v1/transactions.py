"""Transaction, transfer and summary endpoints.

Static paths (``/transactions/summary``, ``/transactions/export.csv``) are
declared before ``/transactions/{id}`` so they never get swallowed by the
dynamic route.
"""

from __future__ import annotations

import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.base import MessageResponse
from app.schemas.transaction import (
    SummaryResponse,
    TransactionCreate,
    TransactionListResponse,
    TransactionResponse,
    TransactionUpdate,
    TransferCreate,
    TransferUpdate,
)
from app.models.transfer import Transfer
from app.services.transfer_service import TransferService
from app.services.transaction_service import (
    TransactionFilters,
    TransactionService,
    serialize_transaction,
    serialize_transfer,
)

router = APIRouter(tags=["transactions"])

EXPORT_COLUMNS = [
    "entity",
    "date",
    "type",
    "amount",
    "description",
    "category",
    "account",
    "destination_account",
    "status",
    "notes",
]


# -- transactions ------------------------------------------------------------


@router.get("/transactions", response_model=TransactionListResponse)
def list_transactions(
    q: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    account_id: int | None = Query(None),
    category_id: int | None = Query(None),
    type: str | None = Query(None, description="income | expense | transfer"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_db),
) -> TransactionListResponse:
    result = TransactionService(session).list(
        TransactionFilters(
            q=q,
            date_from=date_from,
            date_to=date_to,
            account_id=account_id,
            category_id=category_id,
            type=type,
            limit=limit,
            offset=offset,
        )
    )
    return TransactionListResponse(**result)


@router.get("/transactions/summary", response_model=SummaryResponse)
def transaction_summary(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    session: Session = Depends(get_db),
) -> SummaryResponse:
    return SummaryResponse(**TransactionService(session).summary(date_from, date_to))


@router.get("/transactions/export.csv")
def export_transactions_csv(
    q: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    account_id: int | None = Query(None),
    category_id: int | None = Query(None),
    type: str | None = Query(None),
    session: Session = Depends(get_db),
) -> Response:
    """CSV download honouring the same filters as the list endpoint."""
    rows = TransactionService(session).iter_rows(
        TransactionFilters(
            q=q,
            date_from=date_from,
            date_to=date_to,
            account_id=account_id,
            category_id=category_id,
            type=type,
        )
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(EXPORT_COLUMNS)
    for row in rows:
        writer.writerow(
            [
                row["entity"],
                row["date"].isoformat(),
                row["type"],
                f"{row['amount']:.2f}",
                row["description"],
                row["category_name"] or "",
                row["account_name"] or "",
                row["destination_account_name"] or "",
                row["status"],
                row["notes"] or "",
            ]
        )
    filename = "transactions.csv"
    return Response(
        content="\ufeff" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/transactions",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_transaction(
    payload: TransactionCreate, session: Session = Depends(get_db)
) -> TransactionResponse:
    result = TransactionService(session).create(**payload.model_dump())
    if isinstance(result, Transfer):
        return TransactionResponse(**serialize_transfer(result))
    return TransactionResponse(**serialize_transaction(result))


@router.get("/transactions/{transaction_id}", response_model=TransactionResponse)
def get_transaction(
    transaction_id: int, session: Session = Depends(get_db)
) -> TransactionResponse:
    transaction = TransactionService(session).get(transaction_id)
    return TransactionResponse(**serialize_transaction(transaction))


@router.patch("/transactions/{transaction_id}", response_model=TransactionResponse)
def update_transaction(
    transaction_id: int,
    payload: TransactionUpdate,
    session: Session = Depends(get_db),
) -> TransactionResponse:
    fields = payload.model_dump(exclude_unset=True)
    transaction = TransactionService(session).update(transaction_id, **fields)
    return TransactionResponse(**serialize_transaction(transaction))


@router.delete("/transactions/{transaction_id}", response_model=MessageResponse)
def delete_transaction(
    transaction_id: int, session: Session = Depends(get_db)
) -> MessageResponse:
    TransactionService(session).delete(transaction_id)
    return MessageResponse(message="Transaction deleted")


# -- transfers ---------------------------------------------------------------
# Separate endpoints with native transfer statuses; the merged list above
# exposes them as rows with ``entity == "transfer"``.


@router.post(
    "/transfers",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_transfer(
    payload: TransferCreate, session: Session = Depends(get_db)
) -> TransactionResponse:
    transfer = TransferService(session).create(**payload.model_dump())
    return TransactionResponse(**serialize_transfer(transfer))


@router.get("/transfers/{transfer_id}", response_model=TransactionResponse)
def get_transfer(transfer_id: int, session: Session = Depends(get_db)) -> TransactionResponse:
    transfer = TransferService(session).get(transfer_id)
    return TransactionResponse(**serialize_transfer(transfer))


@router.patch("/transfers/{transfer_id}", response_model=TransactionResponse)
def update_transfer(
    transfer_id: int,
    payload: TransferUpdate,
    session: Session = Depends(get_db),
) -> TransactionResponse:
    fields = payload.model_dump(exclude_unset=True)
    transfer = TransferService(session).update(transfer_id, **fields)
    return TransactionResponse(**serialize_transfer(transfer))


@router.delete("/transfers/{transfer_id}", response_model=MessageResponse)
def delete_transfer(
    transfer_id: int, session: Session = Depends(get_db)
) -> MessageResponse:
    TransferService(session).delete(transfer_id)
    return MessageResponse(message="Transfer deleted")
