"""Backup / restore endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.settings import (
    BackupExportResponse,
    BackupRestoreRequest,
    BackupValidateResponse,
)
from app.services.backup_service import BackupService

router = APIRouter(tags=["backup"])


@router.get("/backup/export", response_model=BackupExportResponse)
def export_backup(session: Session = Depends(get_db)) -> BackupExportResponse:
    return BackupExportResponse(**BackupService(session).export())


@router.post("/backup/validate", response_model=BackupValidateResponse)
def validate_backup(
    payload: dict,
    session: Session = Depends(get_db),
) -> BackupValidateResponse:
    return BackupValidateResponse(**BackupService(session).validate(payload))


@router.post("/backup/restore", response_model=BackupValidateResponse)
def restore_backup(
    payload: BackupRestoreRequest,
    session: Session = Depends(get_db),
) -> BackupValidateResponse:
    return BackupValidateResponse(**BackupService(session).restore(payload.payload, confirmed=payload.confirmed))