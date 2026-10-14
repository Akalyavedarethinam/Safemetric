"""Helpers shared by the PDF / DOCX / XLSX report builders."""
from __future__ import annotations

import io

from PIL import Image, ImageDraw

from ..models import Inspection
from ..rules.base import category_config
from ..rules.registry import OVERALL_LABELS
from ..storage import StorageError, get_storage

STATUS_LABEL = {"PASS": "Pass", "NON_COMPLIANT": "Non-compliant", "NEEDS_VERIFICATION": "Needs verification",
                "NOT_APPLICABLE": "Not applicable"}
FIELD_STATUS_LABEL = {"DETECTED": "Detected", "LOW_CONFIDENCE": "Low confidence",
                      "NEEDS_VERIFICATION": "Needs verification", "NOT_DETECTED": "Not detected"}
STATUS_HEX = {"PASS": "#15803d", "NON_COMPLIANT": "#b91c1c", "NEEDS_VERIFICATION": "#b45309", "NOT_APPLICABLE": "#64748b",
              "COMPLIANT": "#15803d", "PARTIALLY_COMPLIANT": "#c2410c",
              "DETECTED": "#15803d", "LOW_CONFIDENCE": "#b45309", "NOT_DETECTED": "#b91c1c"}

LEGEND = [
    ("Detected", "Text read from the package by OCR. Detected information is not by itself a legal verification."),
    ("Pass", "The configured deterministic condition is satisfied by the image evidence."),
    ("Needs verification", "The images are insufficient to decide; physical or authoritative verification is required. "
                           "This is NOT a finding of compliance."),
    ("Non-compliant", "A configured deterministic condition is clearly violated by the evidence shown."),
    ("Not applicable", "The check does not apply to this product/category or was deactivated by an administrator."),
]
DISCLAIMER = ("System-generated inspection report. The compliance decision is produced by a deterministic, rule-based "
              "engine from OCR evidence; no AI model decides compliance. Items marked 'Needs verification' must be "
              "confirmed by an authorised Legal Metrology officer before any enforcement action.")


def meta(insp: Inspection) -> list[tuple[str, str]]:
    return [
        ("Inspection reference", insp.reference),
        ("Inspection date/time", f"{insp.inspection_datetime:%d-%b-%Y %H:%M} UTC" if insp.inspection_datetime else "-"),
        ("Product name", insp.product_name or "-"),
        ("Brand", insp.brand or "-"),
        ("Category", category_config(insp.category)["label"]),
        ("Imported", "Yes" if insp.is_imported else "No"),
        ("Inspecting officer", insp.inspector_name or (insp.inspector.name if insp.inspector else "-")),
        ("Location", insp.location or "-"),
        ("Registration no. (input)", insp.registration_number or "-"),
        ("All panels photographed", "Confirmed by inspector" if insp.all_panels_captured else "Not confirmed"),
        ("Overall status", OVERALL_LABELS.get(insp.overall_status, insp.overall_status)),
        ("Compliance score", f"{insp.score:.1f}% ({insp.earned_points:g} / {insp.applicable_points:g} weighted points)"),
        ("Mean OCR confidence", f"{insp.ocr_confidence:.1f}%"),
        ("Analysed at", f"{insp.analyzed_at:%d-%b-%Y %H:%M:%S} UTC" if insp.analyzed_at else "-"),
    ]


def image_bytes(img, display: bool = True, max_side: int = 900, boxes: list[dict] | None = None) -> bytes | None:
    """Load an inspection image (orientation-corrected) as JPEG, optionally drawing evidence boxes."""
    key = img.display_key if display and img.display_key else img.storage_key
    try:
        data = get_storage().get(key)
        im = Image.open(io.BytesIO(data)).convert("RGB")
    except (StorageError, OSError):
        return None
    if boxes:
        d = ImageDraw.Draw(im)
        for b in boxes:
            x, y, w, h = b["x"], b["y"], b["width"], b["height"]
            d.rectangle([x - 4, y - 4, x + w + 4, y + h + 4], outline=(37, 99, 235), width=max(3, im.width // 300))
    im.thumbnail((max_side, max_side))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=85)
    return out.getvalue()


def crop_bytes(img, bbox: dict, pad: int = 12, max_w: int = 700) -> bytes | None:
    try:
        data = get_storage().get(img.display_key or img.storage_key)
        im = Image.open(io.BytesIO(data)).convert("RGB")
    except (StorageError, OSError):
        return None
    x0, y0 = max(0, bbox["x"] - pad), max(0, bbox["y"] - pad)
    x1, y1 = min(im.width, bbox["x"] + bbox["width"] + pad), min(im.height, bbox["y"] + bbox["height"] + pad)
    if x1 <= x0 or y1 <= y0:
        return None
    c = im.crop((x0, y0, x1, y1))
    if c.width > max_w:
        c = c.resize((max_w, int(c.height * max_w / c.width)))
    out = io.BytesIO()
    c.save(out, "JPEG", quality=88)
    return out.getvalue()
