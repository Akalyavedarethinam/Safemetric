"""Quick single-image label scan (no inspection record is created)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from .. import config
from ..models import User
from ..rules.base import available_categories
from ..security import get_current_user
from ..services import label_scan, ocr, preprocess
from .inspections import _read_upload

router = APIRouter(prefix="/api/ocr", tags=["ocr"])


@router.post("/scan")
async def scan(file: UploadFile = File(...), side: str = Form(default="front"), category: str = Form(default="food"),
               is_imported: bool = Form(default=False), user: User = Depends(get_current_user)):
    """OCR one label photograph and return OCR text (clean + raw), structured fields and potential findings."""
    if category not in {c["key"] for c in available_categories()}:
        raise HTTPException(422, f"Unknown category '{category}'.")
    data, _ = await _read_upload(file, config.ALLOWED_IMAGE_EXT)
    from starlette.concurrency import run_in_threadpool
    try:
        return await run_in_threadpool(label_scan.scan_image, data, side, category, is_imported)
    except preprocess.InvalidImage as exc:
        raise HTTPException(422, str(exc))
    except ocr.OcrUnavailable as exc:
        raise HTTPException(503, str(exc))
