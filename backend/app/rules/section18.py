"""Legal Metrology Act, 2009 - Section 18: declarations must not be misleading (configured expressions)."""
from __future__ import annotations

import re

from .base import NEEDS_VERIFICATION, NON_COMPLIANT, PASS, CheckSpec, Rule, RuleContext

REF = "Legal Metrology Act, 2009 - Section 18 read with PCR 2011"
T = "Misleading / non-standard declarations"


class Section18(Rule):
    rule_no = "S18"
    title = T
    checks = [CheckSpec(
        "S18_MISLEADING", "S18", T, "Configured misleading price expressions", REF, "HIGH",
        "All retail packages", ["full OCR text"],
        "None of the misleading expressions configured in common_rules.json (e.g. 'plus taxes', 'taxes extra') "
        "appear in the OCR text. PASS requires mean OCR confidence ≥ the configured minimum; otherwise the "
        "absence cannot be relied upon.",
        "Review the package for other misleading representations (strike-throughs, stickers over MRP etc.).")]

    def evaluate(self, ctx: RuleContext):
        s = self.checks[0]
        cfg = ctx.common["misleading_expressions"]
        phrases = cfg["tax_exclusive_mrp"] + cfg["price_qualifiers"]
        hits = []
        for img in ctx.images:
            for line in img.lines:
                low = line["text"].lower()
                for ph in phrases:
                    if re.search(rf"(?<!\w){re.escape(ph)}(?!\w)", low):
                        hits.append({"field": "text", "label": f"Expression '{ph}'", "text": line["text"],
                                     "value": ph, "confidence": line["confidence"], "image_id": img.id,
                                     "image": img.name, "side": img.side, "bbox": line["bbox"]})
        if hits:
            return [s.result(NON_COMPLIANT, "Misleading price expression(s) found: "
                             + ", ".join(sorted({h["value"] for h in hits})) + ". MRP must be the maximum price "
                             "inclusive of all taxes.", hits,
                             "Remove wording that implies taxes or charges above the MRP.")]
        if ctx.mean_ocr_confidence >= ctx.common["missing_declaration"]["min_mean_ocr_confidence"]:
            return [s.result(PASS, f"No configured misleading expression found in the OCR text "
                             f"(mean OCR confidence {ctx.mean_ocr_confidence:.0f}%).")]
        return [s.result(NEEDS_VERIFICATION, f"No configured misleading expression found, but mean OCR confidence "
                         f"({ctx.mean_ocr_confidence:.0f}%) is too low to rely on their absence.")]
