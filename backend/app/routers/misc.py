"""Files, dashboard, rules catalogue, users, registration verification, audit log, health."""
from __future__ import annotations

import re
from collections import Counter
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from .. import config, models
from ..database import get_db
from ..models import Inspection, User, utcnow
from ..rules.base import available_categories, category_config, load_config
from ..rules.registry import OVERALL_LABELS, catalogue
from ..security import audit, get_current_user, hash_password, password_problems, require_admin
from ..serializers import inspection_summary, iso, user_out
from ..services.ocr import tesseract_status
from ..services.registration import get_verifier
from ..storage import StorageError, get_storage

router = APIRouter(prefix="/api", tags=["platform"])


# ------------------------------------------------------------------ health
@router.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    t = tesseract_status()
    from ..services import line_roles, ocr, ppocr
    pp = ppocr.status()
    any_ocr = bool(t["available"] or pp.get("available"))
    model = line_roles.load_model()
    ocr_info = {k: v for k, v in t.items() if k != "detail"}
    ocr_info.update({"available": any_ocr, "tesseract_available": t["available"], "engine": config.OCR_ENGINE,
                     "engine_label": ocr.engine_label(), "ppocr": pp})
    return {"status": "ok" if db_ok and any_ocr else "degraded", "app": config.APP_NAME,
            "version": config.APP_VERSION, "database": "ok" if db_ok else "unavailable",
            "database_engine": config.DATABASE_URL.split(":", 1)[0], "storage": config.STORAGE_BACKEND,
            "ocr": ocr_info,
            "line_role_model": {"available": model is not None, **({"trained": model.meta.get("trained"),
                                                                       "sklearn": model.meta.get("sklearn")} if model else {})},
            "time": iso(utcnow())}


@router.get("/meta")
def meta(user: User = Depends(get_current_user)):
    return {"categories": available_categories(), "sides": list(config.PACKAGE_SIDES),
            "max_upload_mb": config.MAX_UPLOAD_MB, "max_images": config.MAX_IMAGES_PER_INSPECTION,
            "allowed_extensions": sorted(config.ALLOWED_IMAGE_EXT), "overall_labels": OVERALL_LABELS}


# ------------------------------------------------------------------ files (authorised download)
@router.get("/files/images/{image_id}")
def get_image(image_id: int, variant: str = "display", user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    img = db.get(models.InspectionImage, image_id)
    if not img:
        raise HTTPException(404, "Image not found.")
    key = img.display_key if variant == "display" and img.display_key else img.storage_key
    try:
        data = get_storage().get(key)
    except StorageError:
        raise HTTPException(404, "Image file is missing from storage.")
    ctype = "image/jpeg" if key == img.display_key else img.content_type
    return Response(data, media_type=ctype, headers={"Cache-Control": "private, max-age=3600"})


@router.get("/files/attachments/{attachment_id}")
def get_attachment(attachment_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.get(models.EvidenceAttachment, attachment_id)
    if not a:
        raise HTTPException(404, "Attachment not found.")
    try:
        data = get_storage().get(a.storage_key)
    except StorageError:
        raise HTTPException(404, "Attachment file is missing from storage.")
    safe = re.sub(r"[^\w.\-]", "_", a.original_filename)
    return Response(data, media_type=a.content_type, headers={"Content-Disposition": f'inline; filename="{safe}"'})


# ------------------------------------------------------------------ dashboard
@router.get("/dashboard")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    done = db.query(Inspection).filter(Inspection.status == "COMPLETED")
    by_status = dict(db.query(Inspection.overall_status, func.count()).filter(Inspection.status == "COMPLETED")
                     .group_by(Inspection.overall_status).all())
    total = db.query(func.count(Inspection.id)).scalar() or 0
    completed = done.count()
    avg = db.query(func.avg(Inspection.score)).filter(Inspection.status == "COMPLETED").scalar() or 0
    by_cat = db.query(Inspection.category, func.count()).group_by(Inspection.category).all()
    since = utcnow() - timedelta(days=13)
    recent_rows = db.query(Inspection.created_at, Inspection.overall_status).filter(Inspection.created_at >= since).all()
    trend = []
    for d in range(14):
        day = (since + timedelta(days=d)).date()
        rows = [r for r in recent_rows if r[0].date() == day]
        trend.append({"date": day.isoformat(), "total": len(rows),
                      "non_compliant": sum(1 for r in rows if r[1] in ("NON_COMPLIANT", "PARTIALLY_COMPLIANT"))})
    violations = db.query(models.RuleFinding.check_id, models.RuleFinding.title, models.RuleFinding.rule_no,
                          func.count()).filter(models.RuleFinding.status == "NON_COMPLIANT") \
        .group_by(models.RuleFinding.check_id, models.RuleFinding.title, models.RuleFinding.rule_no) \
        .order_by(func.count().desc()).limit(8).all()
    recent = db.query(Inspection).order_by(Inspection.created_at.desc()).limit(8).all()
    processing = db.query(func.count(Inspection.id)).filter(Inspection.status == "PROCESSING").scalar() or 0
    mine = db.query(func.count(Inspection.id)).filter(Inspection.user_id == user.id).scalar() or 0
    compliant = by_status.get("COMPLIANT", 0)
    return {
        "total": total, "completed": completed, "processing": processing, "mine": mine,
        "compliant": compliant, "non_compliant": by_status.get("NON_COMPLIANT", 0),
        "partially_compliant": by_status.get("PARTIALLY_COMPLIANT", 0),
        "needs_verification": by_status.get("NEEDS_VERIFICATION", 0),
        "pass_rate": round(compliant / completed * 100, 1) if completed else 0.0,
        "average_score": round(float(avg), 1),
        "by_category": [{"category": c, "label": category_config(c)["label"], "count": n} for c, n in by_cat],
        "trend": trend,
        "top_violations": [{"check_id": c, "title": t, "rule_no": r, "count": n} for c, t, r, n in violations],
        "recent": [inspection_summary(i) for i in recent],
    }


# ------------------------------------------------------------------ rules catalogue
class RuleToggle(BaseModel):
    active: bool


@router.get("/rules")
def rules(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    inactive = {r.check_id for r in db.query(models.RuleSetting).filter_by(active=False)}
    items = catalogue()
    for it in items:
        it["active"] = it["check_id"] not in inactive
    common = load_config("common_rules.json")
    return {"checks": items, "categories": [{**c, "config": category_config(c["key"])} for c in available_categories()],
            "scoring": common["scoring"], "overall_status_rules": common["overall_status_rules"],
            "severity_weights": common["severity_weights"]}


@router.get("/rules/{rule_no}")
def rule_detail(rule_no: str, user: User = Depends(get_current_user)):
    items = [c for c in catalogue() if c["rule_no"].replace("/", "_") == rule_no.replace("/", "_")]
    if not items:
        raise HTTPException(404, "Rule not found.")
    return {"rule_no": items[0]["rule_no"], "title": items[0]["rule_group_title"], "checks": items}


@router.put("/rules/{check_id}")
def toggle_rule(check_id: str, body: RuleToggle, request: Request, admin: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    if check_id not in {c["check_id"] for c in catalogue()}:
        raise HTTPException(404, "Unknown check.")
    s = db.query(models.RuleSetting).filter_by(check_id=check_id).first() or models.RuleSetting(check_id=check_id)
    s.active, s.updated_by = body.active, admin.email
    db.add(s)
    db.commit()
    audit(db, admin, "RULE_TOGGLED", f"{check_id} -> {'active' if body.active else 'inactive'}", request)
    return {"check_id": check_id, "active": body.active}


# ------------------------------------------------------------------ registration (Rule 27 integration point)
class RegistrationIn(BaseModel):
    number: str = Field(min_length=3, max_length=80)


@router.post("/registration/verify")
def verify_registration(body: RegistrationIn, user: User = Depends(get_current_user)):
    return {"number": body.number, **get_verifier().verify(body.number)}


# ------------------------------------------------------------------ user management (admin)
class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(max_length=200)
    password: str
    role: str = "inspector"
    designation: str = "Inspector, Legal Metrology"
    jurisdiction: str = ""
    phone: str = ""


class UserUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    designation: str | None = None
    jurisdiction: str | None = None
    phone: str | None = None
    new_password: str | None = None


@router.get("/users")
def list_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    counts = dict(db.query(Inspection.user_id, func.count()).group_by(Inspection.user_id).all())
    return [{**user_out(u), "inspections": counts.get(u.id, 0)} for u in db.query(User).order_by(User.created_at)]


@router.post("/users", status_code=201)
def create_user(body: UserCreate, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if body.role not in config.ROLES:
        raise HTTPException(422, "Invalid role.")
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(422, "Please enter a valid email address.")
    if (p := password_problems(body.password)):
        raise HTTPException(422, p)
    if db.query(User).filter(func.lower(User.email) == email).first():
        raise HTTPException(409, "An account with this email already exists.")
    u = User(name=body.name, email=email, password_hash=hash_password(body.password), role=body.role,
             designation=body.designation, jurisdiction=body.jurisdiction, phone=body.phone)
    db.add(u)
    db.commit()
    audit(db, admin, "USER_CREATED", f"{email} ({body.role})", request)
    return user_out(u)


@router.put("/users/{user_id}")
def update_user(user_id: int, body: UserUpdate, request: Request, admin: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found.")
    if u.id == admin.id and (body.role not in (None, "admin") or body.is_active is False):
        raise HTTPException(400, "You cannot demote or deactivate your own account.")
    if body.role is not None:
        if body.role not in config.ROLES:
            raise HTTPException(422, "Invalid role.")
        u.role = body.role
    for k in ("name", "is_active", "designation", "jurisdiction", "phone"):
        v = getattr(body, k)
        if v is not None:
            setattr(u, k, v)
    if body.new_password:
        if (p := password_problems(body.new_password)):
            raise HTTPException(422, p)
        u.password_hash = hash_password(body.new_password)
    db.commit()
    audit(db, admin, "USER_UPDATED", u.email, request)
    return user_out(u)


# ------------------------------------------------------------------ audit log
@router.get("/audit")
def audit_log(limit: int = 100, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.query(models.AuditLog).order_by(models.AuditLog.created_at.desc()).limit(min(limit, 500)).all()
    return [{"id": r.id, "user_email": r.user_email, "action": r.action, "detail": r.detail, "ip": r.ip,
             "created_at": iso(r.created_at)} for r in rows]


@router.get("/reports/summary")
def reports_summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Aggregate figures for the Reports page."""
    done = db.query(Inspection).filter(Inspection.status == "COMPLETED").all()
    per_rule = Counter()
    per_rule_nv = Counter()
    for f in db.query(models.RuleFinding.rule_no, models.RuleFinding.status).all():
        if f[1] == "NON_COMPLIANT":
            per_rule[f[0]] += 1
        elif f[1] == "NEEDS_VERIFICATION":
            per_rule_nv[f[0]] += 1
    cats = Counter(i.category for i in done)
    cat_nc = Counter(i.category for i in done if i.overall_status in ("NON_COMPLIANT", "PARTIALLY_COMPLIANT"))
    return {
        "completed": len(done),
        "by_rule": [{"rule_no": r, "non_compliant": per_rule.get(r, 0), "needs_verification": per_rule_nv.get(r, 0)}
                    for r in sorted(set(per_rule) | set(per_rule_nv), key=lambda x: (len(x), x))],
        "by_category": [{"category": c, "label": category_config(c)["label"], "inspections": n,
                         "non_compliant": cat_nc.get(c, 0)} for c, n in cats.most_common()],
        "recent_completed": [inspection_summary(i) for i in sorted(done, key=lambda i: i.analyzed_at or i.created_at,
                                                                   reverse=True)[:25]],
    }
