"""
Single-image label scan: quality -> straighten -> OCR -> clean-up -> field extraction -> structured output ->
potential compliance findings. Nothing is stored. Used by POST /api/ocr/scan and scripts/analyze_label.py.
"""
from __future__ import annotations

import time
from datetime import datetime

from . import extraction, ocr, preprocess, quality, structured


def scan_image(data: bytes, side: str = "front", category: str = "food", is_imported: bool = False,
               engine: str | None = None, with_rules: bool = True) -> dict:
    t0 = time.time()
    bgr = preprocess.load_image(data)                                  # raises InvalidImage with a friendly message
    q = quality.assess_quality(bgr)
    display, orient = preprocess.make_display_image(bgr)
    variants, scale, steps = preprocess.build_variants(display)
    res = ocr.run_ocr(variants, scale, display, engine)
    images = [{"image_id": 1, "image_name": "upload", "side": side, "passes": res["passes"], "merged": res["lines"]}]
    fields = extraction.extract_fields(images, "")
    out = {
        "engine": ocr.engine_label(engine), "seconds": round(time.time() - t0, 2),
        "image": {"width": int(bgr.shape[1]), "height": int(bgr.shape[0]), "display_width": int(display.shape[1]),
                  "display_height": int(display.shape[0]), "quality": q,
                  "preprocessing": orient["steps"] + steps, "geometry": orient.get("geometry")},
        "ocr": {"full_text": res["full_text"], "raw_text": res.get("raw_text", ""), "mean_confidence": res["mean_confidence"],
                "word_count": res["word_count"], "notes": res.get("notes", []),
                "lines": [{"text": l["text"], "raw_text": l.get("raw_text", l["text"]), "confidence": l["confidence"],
                           "bbox": l["bbox"], "engine": l.get("engine", "")} for l in res["lines"]],
                "passes": [{"engine": p.get("engine"), "variant": p.get("variant"), "psm": p.get("psm"),
                            "text": "\n".join(l.get("raw_text", l["text"]) for l in p["lines"])} for p in res["passes"]]},
        "structured": structured.structured_output(fields),
        "structured_detail": structured.structured_detail(fields),
        "fields": {k: v.to_dict() for k, v in fields.items() if v.found},
        "warnings": list(q.get("warnings", [])),
    }
    if res["word_count"] == 0:
        out["warnings"].append("No readable text was found. Retake the photo in even light, fill the frame with the "
                               "label, avoid glare and keep the camera steady.")
    elif res["mean_confidence"] < 60:
        out["warnings"].append("Text was recognised with low confidence - verify the extracted values.")
    if with_rules:
        from ..rules.base import ImageInfo, RuleContext, category_config, load_config
        from ..rules.registry import aggregate, run_rules
        ctx = RuleContext(category=category, is_imported=is_imported, registration_number="", all_panels_captured=False,
                          inspection_date=datetime.utcnow(), product_name="", fields=fields,
                          images=[ImageInfo(id=1, name="upload", side=side, quality_status=q["status"],
                                            width=display.shape[1], height=display.shape[0], panel_width_mm=None,
                                            panel_height_mm=None, mean_confidence=res["mean_confidence"],
                                            lines=res["lines"])],
                          category_cfg=category_config(category), common=load_config("common_rules.json"))
        findings = run_rules(ctx)
        out["potential_findings"] = [
            {"check_id": f["check_id"], "rule_no": f["rule_no"], "title": f["title"], "status": f["status"],
             "severity": f["severity"], "reason": f["reason"],
             "evidence": [e.get("text", "") for e in f.get("evidence", [])][:3]}
            for f in findings if f["status"] in ("NON_COMPLIANT", "NEEDS_VERIFICATION")]
        out["overall_status"] = aggregate(findings)["overall_status"]
        out["disclaimer"] = ("Single-photo scan: missing declarations can only be 'needs verification' because other "
                             "panels were not photographed. Findings are potential findings, not legal judgements.")
    return out
