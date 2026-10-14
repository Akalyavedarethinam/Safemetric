"""
End-to-end analysis pipeline (runs in a background worker thread).

 1. load uploaded images from storage          5. merge OCR text + bounding boxes
 2. image quality check                         6. structured field extraction
 3. preprocessing (orientation, deskew, variants) 7. deterministic rule engine + overall status
 4. multi-pass Tesseract OCR                    8. persist everything, integrity hash

Progress (stage + percentage) is written to the inspection row so the UI can poll it.
"""
from __future__ import annotations

import logging
import threading
import time

import cv2
import numpy as np

from .. import config, models
from ..database import SessionLocal
from ..models import utcnow
from ..rules.base import ImageInfo, RuleContext, category_config, load_config
from ..rules.registry import aggregate, integrity_hash, recommendations, run_rules
from ..storage import get_storage, new_key
from . import extraction, ocr, ppocr, preprocess, quality, structured
from .registration import get_verifier

log = logging.getLogger("safemetric.pipeline")

STAGES = {
    "QUEUED": (2, "Queued"),
    "CHECKING_IMAGES": (8, "Checking image quality"),
    "PREPROCESSING": (15, "Processing images"),
    "OCR": (20, "Running OCR"),
    "EXTRACTING": (82, "Extracting declarations"),
    "RULES": (90, "Checking rules"),
    "SAVING": (96, "Saving inspection"),
    "COMPLETE": (100, "Complete"),
}

_running: set[int] = set()
_running_lock = threading.Lock()


class UserFacingError(RuntimeError):
    """Error whose message is safe to show to the inspector."""


def is_running(inspection_id: int) -> bool:
    with _running_lock:
        return inspection_id in _running


def _set_stage(db, insp, stage: str, pct: int | None = None, detail: str = ""):
    insp.stage = stage
    insp.progress = pct if pct is not None else STAGES[stage][0]
    insp.error = detail if stage == "FAILED" else insp.error
    db.commit()


def start_analysis(inspection_id: int) -> bool:
    with _running_lock:
        if inspection_id in _running:
            return False
        _running.add(inspection_id)
    t = threading.Thread(target=_run_safe, args=(inspection_id,), daemon=True, name=f"analyze-{inspection_id}")
    t.start()
    return True


def _run_safe(inspection_id: int):
    try:
        analyze(inspection_id)
    finally:
        with _running_lock:
            _running.discard(inspection_id)


def analyze(inspection_id: int) -> None:
    db = SessionLocal()
    started = time.time()
    insp = db.get(models.Inspection, inspection_id)
    try:
        if insp is None:
            return
        _reset_results(db, insp)
        insp.status, insp.error = "PROCESSING", ""
        _set_stage(db, insp, "CHECKING_IMAGES")
        if not (ocr.tesseract_status()["available"] or ppocr.available()):
            raise ocr.OcrUnavailable("No OCR engine is available. Install Tesseract (TESSERACT_CMD) or rapidocr_onnxruntime.")
        engine_version = ocr.engine_label()
        storage = get_storage()
        images = list(insp.images)
        if not images:
            raise UserFacingError("No image uploaded. Please upload at least one package photograph.")

        ocr_payload, image_infos, display_cache, failures = [], [], {}, []
        word_total, conf_seen = 0, []
        n = len(images)
        for idx, img in enumerate(images):
            span = (STAGES["EXTRACTING"][0] - STAGES["OCR"][0]) / n
            base_pct = STAGES["OCR"][0] + span * idx
            try:
                data = storage.get(img.storage_key)
                bgr = preprocess.load_image(data)
            except Exception as exc:
                log.warning("image %s unreadable: %s", img.id, exc)
                img.quality_status = "POOR"
                img.quality = {"status": "POOR", "error": str(exc) if isinstance(exc, preprocess.InvalidImage)
                               else "Image could not be read from storage.", "metrics": {}, "warnings": [str(exc)]}
                failures.append(img.original_filename)
                db.commit()
                continue

            _set_stage(db, insp, "CHECKING_IMAGES", int(base_pct))
            q = quality.assess_quality(bgr)
            img.quality_status, img.quality = q["status"], q

            _set_stage(db, insp, "PREPROCESSING", int(base_pct + span * 0.15))
            display, orient = preprocess.make_display_image(bgr)
            variants, scale, steps = preprocess.build_variants(display)
            disp_key = new_key(f"inspections/{insp.id}/display", ".jpg")
            storage.put(disp_key, preprocess.encode_jpeg(display), "image/jpeg")
            img.display_key = disp_key
            img.display_height, img.display_width = display.shape[:2]
            img.rotation_applied = float(orient["geometry"]["angle"]) if orient.get("geometry") else \
                float(orient["rotation"]) + float(orient["skew"])
            img.preprocessing = ["EXIF orientation applied"] + orient["steps"]
            display_cache[img.id] = cv2.cvtColor(display, cv2.COLOR_BGR2GRAY)

            _set_stage(db, insp, "OCR", int(base_pct + span * 0.3))
            result = ocr.run_ocr(variants, scale, display)
            # every pass keeps its own, unmodified OCR reading for debugging ("text" = raw engine output)
            db.add(models.OcrResult(
                image_id=img.id, engine=result.get("engine", config.OCR_ENGINE), engine_version=engine_version,
                full_text=result["full_text"], normalized_text=extraction.normalized_text(result["full_text"]),
                mean_confidence=result["mean_confidence"], word_count=result["word_count"], lines=result["lines"],
                passes=[{"variant": p["variant"], "psm": p["psm"], "engine": p.get("engine", "tesseract"),
                         "description": p.get("description", ""), "lines": len(p["lines"]), "error": p.get("error"),
                         "text": "\n".join(l.get("raw_text", l["text"]) for l in p["lines"])}
                        for p in result["passes"]] + [{"variant": "notes", "psm": None, "engine": "", "description":
                                                      "; ".join(result.get("notes", [])), "lines": 0, "error": None,
                                                      "text": ""}] * bool(result.get("notes")),
            ))
            # record what was actually applied: Tesseract variants only matter when Tesseract ran
            img.preprocessing = list(img.preprocessing) + result.get("preprocessing", []) + \
                (steps if result.get("tesseract_used") else [])
            word_total += result["word_count"]
            conf_seen.append(result["mean_confidence"])
            if result["word_count"] == 0:
                q["warnings"].append("No text could be recognised in this image. Retake it in even light, "
                                     "fill the frame with the label and keep the camera steady.")
            elif result["mean_confidence"] < 60:
                q["warnings"].append("Text was recognised with low confidence - check the extracted values "
                                     "against the package.")
            db.commit()
            ocr_payload.append({"image_id": img.id, "image_name": img.original_filename, "side": img.side,
                                "passes": result["passes"], "merged": result["lines"]})
            image_infos.append(ImageInfo(
                id=img.id, name=img.original_filename, side=img.side, quality_status=img.quality_status,
                width=img.display_width, height=img.display_height, panel_width_mm=img.panel_width_mm,
                panel_height_mm=img.panel_height_mm, mean_confidence=result["mean_confidence"],
                lines=result["lines"], load_gray=(lambda k=img.id: display_cache.get(k))))

        if not image_infos:
            raise UserFacingError("None of the uploaded images could be read. Please upload valid JPG, PNG or WEBP photographs.")

        _set_stage(db, insp, "EXTRACTING")
        fields = extraction.extract_fields(ocr_payload, insp.product_name)
        for fr in fields.values():
            db.add(models.ExtractedField(
                inspection_id=insp.id, field=fr.field, label=fr.label, value=fr.value, normalized=_jsonable(fr.normalized),
                confidence=fr.confidence, status=fr.status, source_image_id=fr.source_image_id,
                source_image=fr.source_image, source_side=fr.source_side, evidence=fr.evidence, bbox=fr.bbox,
                alternatives=_jsonable(fr.alternatives)))
        db.commit()

        _set_stage(db, insp, "RULES")
        ctx = RuleContext(
            category=insp.category, is_imported=bool(insp.is_imported), registration_number=insp.registration_number or "",
            all_panels_captured=bool(insp.all_panels_captured), inspection_date=insp.inspection_datetime or utcnow(),
            product_name=insp.product_name, fields=fields, images=image_infos,
            category_cfg=category_config(insp.category), common=load_config("common_rules.json"),
            registration_verifier=get_verifier())
        inactive = {r.check_id for r in db.query(models.RuleSetting).filter_by(active=False)}
        findings = run_rules(ctx, inactive)
        agg = aggregate(findings)

        _set_stage(db, insp, "SAVING")
        for f in findings:
            db.add(models.RuleFinding(inspection_id=insp.id, **{k: _jsonable(v) for k, v in f.items()}))
        insp.overall_status = agg["overall_status"]
        insp.score, insp.earned_points, insp.applicable_points = agg["score"], agg["earned_points"], agg["applicable_points"]
        c = agg["counts"]
        insp.passed, insp.failed, insp.needs_verification, insp.not_applicable = c["PASS"], c["NON_COMPLIANT"], c["NEEDS_VERIFICATION"], c["NOT_APPLICABLE"]
        insp.ocr_confidence = round(ctx.mean_ocr_confidence, 1)
        insp.recommendations = recommendations(findings)
        ocr_problem = ""
        if word_total == 0:
            ocr_problem = ("No readable text was found in the uploaded photographs, so every declaration is reported as "
                           "'needs verification'. Retake the photos in even light, fill the frame with the label, "
                           "avoid glare and keep the camera steady.")
        elif conf_seen and max(conf_seen) < 60:
            ocr_problem = ("The label text was recognised with low confidence. Extracted values may be wrong - "
                           "compare them with the package or upload clearer photographs.")
        insp.summary = {**agg, "unreadable_images": failures,
                        "structured": structured.structured_detail(fields),
                        "ocr_problem": ocr_problem,
                        "image_quality": {i.side + f"#{i.id}": i.quality_status for i in image_infos},
                        "coverage_conclusive": ctx.coverage_is_conclusive(),
                        "engine": engine_version}
        insp.integrity_hash = integrity_hash({
            "reference": insp.reference, "images": [i.sha256 for i in images],
            "fields": {k: [v.value, v.status] for k, v in fields.items()},
            "findings": [[f["check_id"], f["status"]] for f in findings], "overall": insp.overall_status})
        insp.status = "COMPLETED"
        insp.analyzed_at = utcnow()
        insp.processing_seconds = round(time.time() - started, 1)
        _set_stage(db, insp, "COMPLETE")
        db.add(models.AuditLog(user_id=insp.user_id, action="ANALYZE",
                               detail=f"{insp.reference}: {insp.overall_status} ({insp.score}%) in {insp.processing_seconds}s"))
        db.commit()
    except (ocr.OcrUnavailable, UserFacingError) as exc:
        _fail(db, insp, str(exc))
    except Exception:
        log.exception("analysis of inspection %s failed", inspection_id)
        _fail(db, insp, "Analysis failed due to an internal error. The technical details were logged on the server.")
    finally:
        db.close()


def _fail(db, insp, message: str):
    if insp is None:
        return
    db.rollback()
    insp.status, insp.stage, insp.error = "FAILED", "FAILED", message
    db.commit()


def _reset_results(db, insp):
    for f in list(insp.fields):
        db.delete(f)
    for f in list(insp.findings):
        db.delete(f)
    storage = get_storage()
    for img in insp.images:
        if img.ocr:
            db.delete(img.ocr)
        if img.display_key:
            storage.delete(img.display_key)
            img.display_key = ""
    insp.overall_status, insp.score, insp.recommendations, insp.summary = "", 0.0, [], {}
    db.commit()


def _jsonable(v):
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    return v
