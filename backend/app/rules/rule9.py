"""Rule 9 - Legibility and prominence of declarations (image-based assessment)."""
from __future__ import annotations

import numpy as np

from .base import NEEDS_VERIFICATION, NON_COMPLIANT, PASS, CheckSpec, Rule, RuleContext

REF = "Legal Metrology (Packaged Commodities) Rules, 2011 - Rule 9"
T = "Legibility and prominence of declarations"
KEY_FIELDS = ["net_quantity", "mrp", "mfg_date", "manufacturer_packer", "consumer_care"]


def _luminance(v):
    c = np.asarray(v, dtype=float) / 255.0
    return np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def contrast_ratio(gray, bbox) -> float | None:
    if gray is None or not bbox:
        return None
    x, y, w, h = int(bbox["x"]), int(bbox["y"]), int(bbox["width"]), int(bbox["height"])
    crop = gray[max(0, y):y + h, max(0, x):x + w]
    if crop.size < 30:
        return None
    dark, light = np.percentile(crop, 5), np.percentile(crop, 95)
    l1, l2 = float(_luminance(light)), float(_luminance(dark))
    return round((max(l1, l2) + 0.05) / (min(l1, l2) + 0.05), 2)


class Rule9(Rule):
    rule_no = "9"
    title = T
    checks = [
        CheckSpec("R9_LEGIBILITY", "9", T, "Legibility of mandatory declarations", REF, "HIGH",
                  "All retail packages", KEY_FIELDS,
                  "Every extracted key declaration has OCR confidence ≥ threshold and text/background contrast ratio "
                  "≥ threshold (configured in common_rules.json) on a non-POOR image. NON_COMPLIANT only if contrast "
                  "is below the configured hard minimum on a GOOD quality image.",
                  "Visually confirm legibility under normal lighting."),
        CheckSpec("R9_PROMINENCE", "9", T, "Prominence of the net quantity declaration", REF, "MEDIUM",
                  "All retail packages", ["net_quantity"],
                  "Net-quantity numeral height ≥ median text height on the same panel.",
                  "Visually confirm that the net quantity is conspicuous."),
    ]

    def evaluate(self, ctx: RuleContext):
        cfg = ctx.common["legibility"]
        out = []
        s = self.spec("R9_LEGIBILITY")
        measured, weak, hard_fail = [], [], []
        gray_cache = {}
        for name in KEY_FIELDS:
            f = ctx.field(name)
            if not f or not f.found or not f.bbox:
                continue
            img = ctx.image(f.source_image_id)
            if img and img.id not in gray_cache:
                gray_cache[img.id] = img.load_gray() if img.load_gray else None
            cr = contrast_ratio(gray_cache.get(img.id) if img else None, f.bbox)
            measured.append((f, cr, img))
            if f.confidence < cfg["min_field_confidence_for_pass"] or (cr is not None and cr < cfg["min_contrast_ratio_for_pass"]):
                weak.append((f, cr))
            if cr is not None and cr < cfg["non_compliant_contrast_ratio"] and img and img.quality_status == "GOOD":
                hard_fail.append((f, cr))
        ev = []
        for f, cr, _ in measured:
            e = ctx.evidence(f.field)[0]
            e["contrast_ratio"] = cr
            ev.append(e)
        summary = "; ".join(f"{f.label}: OCR {f.confidence:.0f}%, contrast {cr if cr is not None else 'n/a'}:1"
                            for f, cr, _ in measured)
        if not measured:
            out.append(s.result(NEEDS_VERIFICATION, "No key declarations were extracted, legibility cannot be assessed from the images."))
        elif hard_fail:
            out.append(s.result(NON_COMPLIANT, "Text/background contrast below the configured minimum "
                                f"{cfg['non_compliant_contrast_ratio']}:1 on a good-quality image for: "
                                + ", ".join(f"{f.label} ({cr}:1)" for f, cr in hard_fail) + ".", ev,
                                "Print mandatory declarations in a colour that contrasts clearly with the background."))
        elif weak or any(img and img.quality_status == "POOR" for _, _, img in measured):
            out.append(s.result(NEEDS_VERIFICATION, "Image-based legibility indicators are inconclusive for some "
                                f"declarations. {summary}.", ev, "Visually confirm legibility of the flagged declarations."))
        else:
            missing = [n for n in KEY_FIELDS if not ctx.field(n).found]
            note = f" Not assessed (not extracted): {', '.join(missing)}." if missing else ""
            out.append(s.result(PASS if not missing else NEEDS_VERIFICATION,
                                f"Extracted declarations meet the configured legibility indicators. {summary}.{note}", ev))

        s = self.spec("R9_PROMINENCE")
        q = ctx.field("net_quantity")
        img = ctx.image(q.source_image_id) if q.found else None
        px = q.normalized.get("letter_height_px") if q.found else None
        if not (q.found and img and px and img.lines):
            out.append(s.result(NEEDS_VERIFICATION, "Net quantity or panel text not available to assess prominence."))
        else:
            heights = [w["bbox"]["height"] for l in img.lines for w in l.get("words", []) if any(c.isalnum() for c in w["text"])]
            median = float(np.median(heights)) if heights else 0
            ratio = px / median if median else 0
            if ratio >= 1.0:
                out.append(s.result(PASS, f"Net-quantity numerals ({px:.0f} px) are {ratio:.1f}× the median text height "
                                    f"({median:.0f} px) on the {img.side} panel.", ctx.evidence("net_quantity")))
            else:
                out.append(s.result(NEEDS_VERIFICATION, f"Net-quantity numerals ({px:.0f} px) are smaller than the median "
                                    f"text height ({median:.0f} px) on the {img.side} panel.", ctx.evidence("net_quantity"),
                                    "Confirm the net quantity is displayed conspicuously."))
        return out
