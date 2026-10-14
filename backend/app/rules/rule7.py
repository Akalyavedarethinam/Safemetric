"""Rule 7 - Size of letters and numerals (principal display panel)."""
from __future__ import annotations

from .base import NEEDS_VERIFICATION, NON_COMPLIANT, PASS, CheckSpec, Rule, RuleContext, load_config

REF = "Legal Metrology (Packaged Commodities) Rules, 2011 - Rule 7"
NO_SCALE = "Requires reliable physical scale/reference for letter/numeral height."


class Rule7(Rule):
    rule_no = "7"
    title = "Principal display panel - size of letters and numerals"
    checks = [CheckSpec(
        "R7_LETTER_HEIGHT", "7", title, "Minimum height of numerals in the net quantity declaration", REF, "HIGH",
        "All retail packages",
        ["net_quantity", "image calibration (panel width/height in mm)"],
        "Measured numeral height (pixels × mm-per-pixel from inspector calibration) ≥ minimum in the configured "
        "Rule 7 table. Without a physical calibration the check cannot be decided.",
        "Measure the height of the net-quantity numerals with a scale/vernier on the physical package.")]

    def evaluate(self, ctx: RuleContext):
        spec = self.checks[0]
        q = ctx.field("net_quantity")
        if not q.found or q.normalized.get("unparsed"):
            return [spec.result(NEEDS_VERIFICATION, f"Net quantity declaration not extracted; {NO_SCALE}")]
        img = ctx.image(q.source_image_id)
        px = q.normalized.get("letter_height_px")
        ev = ctx.evidence("net_quantity")
        if not img or not px:
            return [spec.result(NEEDS_VERIFICATION, NO_SCALE, ev)]
        scales = []
        if img.panel_width_mm:
            scales.append(img.panel_width_mm / img.width)
        if img.panel_height_mm:
            scales.append(img.panel_height_mm / img.height)
        if not scales:
            return [spec.result(NEEDS_VERIFICATION,
                                f"{NO_SCALE} The numerals measure {px:.0f} px in the photograph, but no physical "
                                f"dimension of the '{img.side}' panel was supplied to convert pixels to millimetres.", ev)]
        mm_per_px = sum(scales) / len(scales)
        measured = px * mm_per_px
        cfg = load_config("rule7_letter_height.json")
        if img.panel_width_mm and img.panel_height_mm:
            area = img.panel_width_mm * img.panel_height_mm / 100.0
            table, basis, key = cfg["pdp_area_cm2"], f"principal display panel area {area:.0f} cm²", area
        else:
            base = q.normalized.get("base_value") or 0
            if q.normalized.get("dimension") not in ("mass", "volume"):
                return [spec.result(NEEDS_VERIFICATION, "Panel area is required for quantities declared by number/length; "
                                    "supply both panel width and height.", ev)]
            table, basis, key = cfg["net_quantity_g_or_ml"], f"net quantity {q.value}", base
        row = next(r for r in table if r["max"] is None or key <= r["max"])
        required = row["normal_mm"]
        tol = cfg["tolerance"]
        detail = (f"Measured numeral height ≈ {measured:.2f} mm ({px:.0f} px × {mm_per_px:.4f} mm/px, calibrated from "
                  f"the inspector-supplied panel size); required minimum for {basis}: {required} mm.")
        if measured >= required:
            return [spec.result(PASS, detail + " Requirement met.", ev,
                                verification="Result depends on the accuracy of the supplied panel dimensions.")]
        if measured < required * (1 - tol):
            return [spec.result(NON_COMPLIANT, detail + f" Below the minimum by more than the {tol:.0%} measurement tolerance.",
                                ev, f"Increase the height of the net-quantity numerals to at least {required} mm.")]
        return [spec.result(NEEDS_VERIFICATION, detail + " Within measurement tolerance - confirm with a physical measurement.", ev)]
