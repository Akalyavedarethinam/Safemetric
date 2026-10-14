"""Model -> JSON conversion (kept separate from routers so reports can reuse it)."""
from __future__ import annotations

from .models import EvidenceAttachment, Inspection, InspectionImage, User
from .rules.base import category_config
from .rules.registry import OVERALL_LABELS
from .services.pipeline import STAGES


def iso(dt):
    return dt.isoformat() + "Z" if dt else None


def user_out(u: User) -> dict:
    return {"id": u.id, "name": u.name, "email": u.email, "role": u.role, "designation": u.designation,
            "jurisdiction": u.jurisdiction, "phone": u.phone, "is_active": u.is_active,
            "created_at": iso(u.created_at), "last_login": iso(u.last_login)}


def image_out(img: InspectionImage, with_ocr: bool = False) -> dict:
    d = {"id": img.id, "side": img.side, "filename": img.original_filename, "content_type": img.content_type,
         "size_bytes": img.size_bytes, "width": img.width, "height": img.height,
         "display_width": img.display_width or img.width, "display_height": img.display_height or img.height,
         "has_display": bool(img.display_key), "sha256": img.sha256,
         "panel_width_mm": img.panel_width_mm, "panel_height_mm": img.panel_height_mm,
         "quality_status": img.quality_status, "quality": img.quality or {}, "preprocessing": img.preprocessing or [],
         "rotation_applied": img.rotation_applied, "created_at": iso(img.created_at)}
    if with_ocr:
        o = img.ocr
        d["ocr"] = None if o is None else {
            "engine": f"{o.engine} {o.engine_version}".strip(), "full_text": o.full_text,
            "normalized_text": o.normalized_text, "mean_confidence": o.mean_confidence, "word_count": o.word_count,
            "lines": o.lines, "passes": o.passes}
    return d


def attachment_out(a: EvidenceAttachment) -> dict:
    return {"id": a.id, "filename": a.original_filename, "content_type": a.content_type, "size_bytes": a.size_bytes,
            "caption": a.caption, "uploaded_by": a.uploaded_by, "created_at": iso(a.created_at)}


def inspection_summary(i: Inspection) -> dict:
    return {
        "id": i.id, "reference": i.reference, "product_name": i.product_name, "brand": i.brand,
        "category": i.category, "category_label": category_config(i.category)["label"],
        "is_imported": i.is_imported, "inspector_name": i.inspector_name, "user_id": i.user_id,
        "inspection_datetime": iso(i.inspection_datetime), "location": i.location,
        "status": i.status, "stage": i.stage, "progress": i.progress,
        "stage_label": STAGES.get(i.stage, (0, i.stage.title() if i.stage else ""))[1],
        "overall_status": i.overall_status, "overall_label": OVERALL_LABELS.get(i.overall_status, ""),
        "score": i.score, "passed": i.passed, "failed": i.failed, "needs_verification": i.needs_verification,
        "not_applicable": i.not_applicable, "ocr_confidence": i.ocr_confidence,
        "image_count": len(i.images), "manufacturer": next((f.value for f in i.fields if f.field == "manufacturer_packer" and f.value), ""),
        "created_at": iso(i.created_at), "analyzed_at": iso(i.analyzed_at), "error": i.error,
    }


def inspection_detail(i: Inspection, with_ocr: bool = True) -> dict:
    d = inspection_summary(i)
    d.update({
        "manufacturer_info": i.manufacturer_info, "registration_number": i.registration_number, "notes": i.notes,
        "all_panels_captured": i.all_panels_captured, "earned_points": i.earned_points,
        "applicable_points": i.applicable_points, "summary": i.summary or {}, "recommendations": i.recommendations or [],
        "integrity_hash": i.integrity_hash, "processing_seconds": i.processing_seconds,
        "images": [image_out(img, with_ocr) for img in i.images],
        "fields": [{"field": f.field, "label": f.label, "value": f.value, "normalized": f.normalized,
                    "confidence": f.confidence, "status": f.status, "source_image_id": f.source_image_id,
                    "source_image": f.source_image, "source_side": f.source_side, "evidence": f.evidence,
                    "bbox": f.bbox, "alternatives": f.alternatives} for f in i.fields],
        "findings": [{"id": f.id, "check_id": f.check_id, "rule_no": f.rule_no, "rule_title": f.rule_title,
                      "title": f.title, "reference": f.reference, "severity": f.severity, "weight": f.weight,
                      "applicable": f.applicable, "applicability": f.applicability, "required_data": f.required_data,
                      "condition": f.condition, "status": f.status, "reason": f.reason,
                      "verification": f.verification, "evidence": f.evidence, "recommendation": f.recommendation}
                     for f in i.findings],
        "attachments": [attachment_out(a) for a in i.attachments],
        "inspector": user_out(i.inspector) if i.inspector else None,
    })
    return d
