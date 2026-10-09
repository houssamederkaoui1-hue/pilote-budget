"""CSV import endpoints (inspect -> preview -> commit).

Stateless by design: the file is re-uploaded on every call together with the
explicit mapping produced by the previous step.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.errors import ValidationError
from app.schemas.importing import (
    ImportCommitResponse,
    ImportInspectResponse,
    ImportMappingPayload,
    ImportPreviewResponse,
)
from app.services.import_service import ImportService

router = APIRouter(prefix="/imports", tags=["imports"])

MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def _read_upload(upload: UploadFile) -> bytes:
    data = upload.file.read(MAX_UPLOAD_BYTES + 1)
    if not data:
        raise ValidationError("Uploaded file is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File is too large (limit {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)",
        )
    return data


def _parse_mapping(raw: str) -> dict:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"mapping must be valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValidationError("mapping must be a JSON object")
    try:
        return ImportMappingPayload.model_validate(payload).model_dump()
    except PydanticValidationError as exc:
        first = exc.errors()[0] if exc.errors() else {}
        location = ".".join(str(part) for part in first.get("loc", []) if part not in ("body", "__root__"))
        message = first.get("msg", "invalid mapping")
        raise ValidationError(
            f"Invalid mapping{(f' ({location})' if location else '')}: {message}"
        ) from exc


@router.post("/inspect", response_model=ImportInspectResponse)
def inspect_import(
    file: UploadFile = File(...),
    encoding: str = Form("auto"),
    session: Session = Depends(get_db),
) -> ImportInspectResponse:
    result = ImportService(session).inspect(
        _read_upload(file),
        filename=file.filename,
        encoding=encoding,
    )
    return ImportInspectResponse(**result)


@router.post("/preview", response_model=ImportPreviewResponse)
def preview_import(
    file: UploadFile = File(...),
    mapping: str = Form(...),
    session: Session = Depends(get_db),
) -> ImportPreviewResponse:
    payload = _parse_mapping(mapping)
    result = ImportService(session).preview(_read_upload(file), payload)
    return ImportPreviewResponse(**result)


@router.post("/commit", response_model=ImportCommitResponse)
def commit_import(
    file: UploadFile = File(...),
    mapping: str = Form(...),
    session: Session = Depends(get_db),
) -> ImportCommitResponse:
    payload = _parse_mapping(mapping)
    result = ImportService(session).commit(_read_upload(file), payload)
    return ImportCommitResponse(**result)
