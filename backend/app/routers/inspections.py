from __future__ import annotations

import csv
import hashlib
import io
import logging
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import asc, desc, func, or_
from sqlalchemy.orm import Session, selectinload

from .. import config, models
from ..database import get_db
from ..models import Inspection, InspectionImage, User, utcnow
from ..reports import docx_report, pdf_report, xlsx_report
from ..rules.base import available_categories
from ..security import audit, get_current_user
from ..serializers import attachment_out, image_out, inspection_detail, inspection_summary
from ..services import pipeline, preprocess
from ..storage import get_storage, new_key

log = logging.getLogger("safemetric.api")
router = APIRouter(prefix="/api/inspections", tags=["inspections"])
CATEGORY_KEYS = {c["key"] for c in available_categories()}


class InspectionIn(BaseModel):
    product_name: str = Field(default="", max_length=200)
    brand: str = Field(default="", max_length=160)
    category: str = Field(default="other", max_length=40)
    manufacturer_info: str = Field(default="", max_length=400)
    is_imported: bool = False
    registration_number: str = Field(default="", max_length=80)
    inspector_name: str = Field(default="", max_length=120)
    inspection_datetime: datetime | None = None
    location: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=4000)
    all_panels_captured: bool = False


class ImagePatch(BaseModel):
    side: str | None = None
    panel_width_mm: float | None = Field(default=None, ge=0, le=5000)
    panel_height_mm: float | None = Field(default=None, ge=0, le=5000)


def _next_reference(db: Session) -> str:
    n = (db.query(func.max(Inspection.id)).scalar() or 0) + 1
    return f"INS-{utcnow():%Y}-{n:06d}"


def _get(db: Session, inspection_id: int) -> Inspection:
    insp = db.query(Inspection).options(
        selectinload(Inspection.images).selectinload(InspectionImage.ocr),
        selectinload(Inspection.fields), selectinload(Inspection.findings),
        selectinload(Inspection.attachments)).filter(Inspection.id == inspection_id).first()
    if not insp:
        raise HTTPException(404, "Inspection record not found.")
    return insp


def _can_edit(user: User, insp: Inspection):
    if user.role != "admin" and insp.user_id != user.id:
        raise HTTPException(403, "Only the inspecting officer or an administrator can modify this inspection.")


def _validate(body: InspectionIn):
    if body.category not in CATEGORY_KEYS:
        raise HTTPException(422, f"Unknown product category '{body.category}'.")


# --------------------------------------------------------------------------- create / list
@router.post("", status_code=201)
def create_inspection(body: InspectionIn, request: Request, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    _validate(body)
    insp = Inspection(**body.model_dump(exclude={"inspection_datetime"}),
                      inspection_datetime=(body.inspection_datetime.replace(tzinfo=None) if body.inspection_datetime else utcnow()),
                      user_id=user.id, status="DRAFT", reference="TMP")
    if not insp.inspector_name:
        insp.inspector_name = user.name
    db.add(insp)
    db.flush()
    insp.reference = f"INS-{utcnow():%Y}-{insp.id:06d}"
    db.commit()
    audit(db, user, "INSPECTION_CREATED", insp.reference, request)
    return inspection_detail(_get(db, insp.id))


@router.get("")
def list_inspections(
    q: str = "", status: str = "", category: str = "", processing: str = "",
    date_from: str = "", date_to: str = "", mine: bool = False,
    sort: str = Query("created_at", pattern="^(created_at|reference|product_name|brand|category|overall_status|score|inspector_name)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    query = db.query(Inspection).options(selectinload(Inspection.images), selectinload(Inspection.fields))
    if q:
        like = f"%{q.strip()}%"
        sub = db.query(models.ExtractedField.inspection_id).filter(
            models.ExtractedField.field.in_(["manufacturer_packer", "importer"]), models.ExtractedField.value.ilike(like))
        query = query.filter(or_(Inspection.reference.ilike(like), Inspection.product_name.ilike(like),
                                 Inspection.brand.ilike(like), Inspection.inspector_name.ilike(like),
                                 Inspection.location.ilike(like), Inspection.id.in_(sub)))
    if status:
        query = query.filter(Inspection.overall_status == status)
    if category:
        query = query.filter(Inspection.category == category)
    if processing:
        query = query.filter(Inspection.status == processing)
    if mine:
        query = query.filter(Inspection.user_id == user.id)
    try:
        if date_from:
            query = query.filter(Inspection.created_at >= datetime.fromisoformat(date_from))
        if date_to:
            query = query.filter(Inspection.created_at < datetime.fromisoformat(date_to) + timedelta(days=1))
    except ValueError:
        raise HTTPException(422, "Dates must be in YYYY-MM-DD format.")
    total = query.count()
    col = getattr(Inspection, sort)
    query = query.order_by(asc(col) if order == "asc" else desc(col), desc(Inspection.id))
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [inspection_summary(i) for i in items], "total": total, "page": page, "page_size": page_size}


@router.get("/export.csv")
def export_csv(q: str = "", status: str = "", category: str = "", user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    data = list_inspections(q=q, status=status, category=category, processing="", date_from="", date_to="",
                            mine=False, sort="created_at", order="desc", page=1, page_size=200, user=user, db=db)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Reference", "Product", "Brand", "Category", "Overall status", "Score %", "Passed", "Non-compliant",
                "Needs verification", "Inspector", "Inspection date", "Images", "Manufacturer"])
    for i in data["items"]:
        w.writerow([i["reference"], i["product_name"], i["brand"], i["category_label"], i["overall_label"] or i["status"],
                    i["score"], i["passed"], i["failed"], i["needs_verification"], i["inspector_name"],
                    i["inspection_datetime"], i["image_count"], i["manufacturer"]])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="safemetric_inspections.csv"'})


# --------------------------------------------------------------------------- read / update / delete
@router.get("/{inspection_id}")
def get_inspection(inspection_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return inspection_detail(_get(db, inspection_id))


@router.put("/{inspection_id}")
def update_inspection(inspection_id: int, body: InspectionIn, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    _validate(body)
    insp = _get(db, inspection_id)
    _can_edit(user, insp)
    for k, v in body.model_dump(exclude={"inspection_datetime"}).items():
        setattr(insp, k, v)
    if body.inspection_datetime:
        insp.inspection_datetime = body.inspection_datetime.replace(tzinfo=None)
    db.commit()
    return inspection_detail(_get(db, inspection_id))


@router.delete("/{inspection_id}")
def delete_inspection(inspection_id: int, request: Request, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    insp = _get(db, inspection_id)
    _can_edit(user, insp)
    if pipeline.is_running(inspection_id):
        raise HTTPException(409, "Analysis is in progress; try again when it finishes.")
    storage = get_storage()
    for img in insp.images:
        storage.delete(img.storage_key)
        if img.display_key:
            storage.delete(img.display_key)
    for a in insp.attachments:
        storage.delete(a.storage_key)
    ref = insp.reference
    db.delete(insp)
    db.commit()
    audit(db, user, "INSPECTION_DELETED", ref, request)
    return {"ok": True}


# --------------------------------------------------------------------------- images
async def _read_upload(file: UploadFile, allowed_ext: set[str]) -> tuple[bytes, str]:
    name = Path(file.filename or "upload").name
    ext = Path(name).suffix.lower()
    if ext not in allowed_ext:
        raise HTTPException(415, f"Unsupported file type '{ext or 'unknown'}'. Allowed: {', '.join(sorted(allowed_ext))}.")
    data = await file.read(config.MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if not data:
        raise HTTPException(422, f"'{name}' is empty.")
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"'{name}' exceeds the {config.MAX_UPLOAD_MB} MB size limit.")
    return data, name


@router.post("/{inspection_id}/images", status_code=201)
async def upload_images(inspection_id: int, request: Request,
                        files: list[UploadFile] = File(...), sides: list[str] = Form(default=[]),
                        panel_width_mm: list[str] = Form(default=[]), panel_height_mm: list[str] = Form(default=[]),
                        user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    insp = _get(db, inspection_id)
    _can_edit(user, insp)
    if pipeline.is_running(inspection_id):
        raise HTTPException(409, "Analysis is in progress.")
    if not files:
        raise HTTPException(422, "No image uploaded.")
    if len(insp.images) + len(files) > config.MAX_IMAGES_PER_INSPECTION:
        raise HTTPException(422, f"A maximum of {config.MAX_IMAGES_PER_INSPECTION} images per inspection is allowed.")
    storage = get_storage()
    created = []

    def _num(lst, i):
        try:
            v = float(lst[i]) if i < len(lst) and str(lst[i]).strip() else None
            return v if v and v > 0 else None
        except ValueError:
            return None

    for i, f in enumerate(files):
        data, name = await _read_upload(f, config.ALLOWED_IMAGE_EXT)
        try:
            bgr = preprocess.load_image(data)
        except preprocess.InvalidImage as exc:
            raise HTTPException(422, f"'{name}': {exc}")
        side = (sides[i] if i < len(sides) else "front").lower()
        if side not in config.PACKAGE_SIDES:
            raise HTTPException(422, f"Invalid package side '{side}'.")
        ext = Path(name).suffix.lower()
        key = new_key(f"inspections/{insp.id}/original", ext)
        ctype = {".png": "image/png", ".webp": "image/webp"}.get(ext, "image/jpeg")
        storage.put(key, data, ctype)
        img = InspectionImage(inspection_id=insp.id, side=side, original_filename=name, storage_key=key,
                              content_type=ctype, size_bytes=len(data), height=bgr.shape[0], width=bgr.shape[1],
                              sha256=hashlib.sha256(data).hexdigest(),
                              panel_width_mm=_num(panel_width_mm, i), panel_height_mm=_num(panel_height_mm, i))
        db.add(img)
        created.append(img)
    db.commit()
    audit(db, user, "IMAGES_UPLOADED", f"{insp.reference}: {len(created)} image(s)", request)
    return [image_out(i) for i in created]


@router.get("/{inspection_id}/images")
def list_images(inspection_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [image_out(i, with_ocr=True) for i in _get(db, inspection_id).images]


@router.patch("/{inspection_id}/images/{image_id}")
def patch_image(inspection_id: int, image_id: int, body: ImagePatch, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    insp = _get(db, inspection_id)
    _can_edit(user, insp)
    img = next((i for i in insp.images if i.id == image_id), None)
    if not img:
        raise HTTPException(404, "Image not found.")
    if body.side:
        if body.side not in config.PACKAGE_SIDES:
            raise HTTPException(422, "Invalid package side.")
        img.side = body.side
    img.panel_width_mm = body.panel_width_mm or None
    img.panel_height_mm = body.panel_height_mm or None
    db.commit()
    return image_out(img)


@router.delete("/{inspection_id}/images/{image_id}")
def delete_image(inspection_id: int, image_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    insp = _get(db, inspection_id)
    _can_edit(user, insp)
    img = next((i for i in insp.images if i.id == image_id), None)
    if not img:
        raise HTTPException(404, "Image not found.")
    storage = get_storage()
    storage.delete(img.storage_key)
    if img.display_key:
        storage.delete(img.display_key)
    db.delete(img)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- analysis
@router.post("/{inspection_id}/analyze", status_code=202)
def analyze(inspection_id: int, request: Request, sync: bool = False, user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    insp = _get(db, inspection_id)
    _can_edit(user, insp)
    if not insp.images:
        raise HTTPException(422, "No image uploaded. Please upload at least one package photograph before analysing.")
    if not (insp.product_name or insp.brand) and not insp.category:
        raise HTTPException(422, "Missing product information: enter a product name or category.")
    if pipeline.is_running(inspection_id):
        raise HTTPException(409, "Analysis is already running for this inspection.")
    insp.status, insp.stage, insp.progress, insp.error = "PROCESSING", "QUEUED", 2, ""
    db.commit()
    audit(db, user, "ANALYZE_REQUESTED", insp.reference, request)
    if sync:
        pipeline.analyze(inspection_id)
        db.expire_all()
        return inspection_detail(_get(db, inspection_id))
    pipeline.start_analysis(inspection_id)
    return {"id": inspection_id, "status": "PROCESSING", "stage": "QUEUED", "progress": 2}


@router.get("/{inspection_id}/progress")
def progress(inspection_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    insp = db.get(Inspection, inspection_id)
    if not insp:
        raise HTTPException(404, "Inspection record not found.")
    db.refresh(insp)
    return {"id": insp.id, "status": insp.status, "stage": insp.stage, "progress": insp.progress,
            "stage_label": pipeline.STAGES.get(insp.stage, (0, insp.stage))[1], "error": insp.error,
            "running": pipeline.is_running(inspection_id)}


@router.get("/{inspection_id}/results")
def results(inspection_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    insp = _get(db, inspection_id)
    if insp.status != "COMPLETED":
        raise HTTPException(409, f"Results are not available yet (status: {insp.status}).")
    d = inspection_detail(insp, with_ocr=False)
    return {k: d[k] for k in ("id", "reference", "overall_status", "overall_label", "score", "earned_points",
                              "applicable_points", "passed", "failed", "needs_verification", "not_applicable",
                              "summary", "fields", "findings", "recommendations", "integrity_hash")}


# --------------------------------------------------------------------------- supporting evidence
@router.post("/{inspection_id}/attachments", status_code=201)
async def add_attachment(inspection_id: int, file: UploadFile = File(...), caption: str = Form(default=""),
                         user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    insp = _get(db, inspection_id)
    _can_edit(user, insp)
    data, name = await _read_upload(file, config.ALLOWED_EVIDENCE_EXT)
    ext = Path(name).suffix.lower()
    if ext != ".pdf":
        try:
            preprocess.load_image(data)
        except preprocess.InvalidImage as exc:
            raise HTTPException(422, f"'{name}': {exc}")
    elif not data.startswith(b"%PDF"):
        raise HTTPException(422, f"'{name}' is not a valid PDF file.")
    ctype = {".pdf": "application/pdf", ".png": "image/png", ".webp": "image/webp"}.get(ext, "image/jpeg")
    key = new_key(f"inspections/{insp.id}/evidence", ext)
    get_storage().put(key, data, ctype)
    a = models.EvidenceAttachment(inspection_id=insp.id, storage_key=key, original_filename=name, content_type=ctype,
                                  size_bytes=len(data), caption=caption[:300], uploaded_by=user.name)
    db.add(a)
    db.commit()
    return attachment_out(a)


@router.delete("/{inspection_id}/attachments/{attachment_id}")
def delete_attachment(inspection_id: int, attachment_id: int, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    insp = _get(db, inspection_id)
    _can_edit(user, insp)
    a = next((x for x in insp.attachments if x.id == attachment_id), None)
    if not a:
        raise HTTPException(404, "Attachment not found.")
    get_storage().delete(a.storage_key)
    db.delete(a)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- reports
def _report_ready(insp: Inspection):
    if insp.status != "COMPLETED":
        raise HTTPException(409, "Run the analysis before generating a report.")


@router.get("/{inspection_id}/report.pdf")
def report_pdf(inspection_id: int, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    insp = _get(db, inspection_id)
    _report_ready(insp)
    pdf = pdf_report.build(insp, generated_by=user.name)
    audit(db, user, "REPORT_PDF", insp.reference, request)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{insp.reference}_report.pdf"'})


@router.get("/{inspection_id}/report.docx")
def report_docx(inspection_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    insp = _get(db, inspection_id)
    _report_ready(insp)
    return Response(docx_report.build(insp, generated_by=user.name),
                    media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="{insp.reference}_report.docx"'})


@router.get("/{inspection_id}/report.xlsx")
def report_xlsx(inspection_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    insp = _get(db, inspection_id)
    _report_ready(insp)
    return Response(xlsx_report.build(insp),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{insp.reference}_report.xlsx"'})
