"""Account endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.account import AccountCreate, AccountResponse, AccountUpdate
from app.schemas.base import MessageResponse
from app.services.account_service import AccountService

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountResponse])
def list_accounts(
    include_archived: bool = Query(False),
    type: str | None = Query(None),
    session: Session = Depends(get_db),
) -> list[AccountResponse]:
    accounts = AccountService(session).list(include_archived=include_archived, type=type)
    return [AccountResponse.model_validate(account) for account in accounts]


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def create_account(
    payload: AccountCreate, session: Session = Depends(get_db)
) -> AccountResponse:
    account = AccountService(session).create(**payload.model_dump())
    return AccountResponse.model_validate(account)


@router.get("/{account_id}", response_model=AccountResponse)
def get_account(account_id: int, session: Session = Depends(get_db)) -> AccountResponse:
    account = AccountService(session).get(account_id)
    return AccountResponse.model_validate(account)


@router.patch("/{account_id}", response_model=AccountResponse)
def update_account(
    account_id: int,
    payload: AccountUpdate,
    session: Session = Depends(get_db),
) -> AccountResponse:
    fields = payload.model_dump(exclude_unset=True)
    account = AccountService(session).update(account_id, **fields)
    return AccountResponse.model_validate(account)


@router.delete("/{account_id}", response_model=MessageResponse)
def delete_account(account_id: int, session: Session = Depends(get_db)) -> MessageResponse:
    AccountService(session).delete(account_id)
    return MessageResponse(message="Account deleted")


@router.post("/{account_id}/archive", response_model=AccountResponse)
def archive_account(account_id: int, session: Session = Depends(get_db)) -> AccountResponse:
    """Soft-delete: keeps history, hides the account from active lists."""
    account = AccountService(session).archive(account_id, active=False)
    return AccountResponse.model_validate(account)


@router.post("/{account_id}/activate", response_model=AccountResponse)
def activate_account(account_id: int, session: Session = Depends(get_db)) -> AccountResponse:
    account = AccountService(session).archive(account_id, active=True)
    return AccountResponse.model_validate(account)
