"""Rules 11 & 12 - Units and manner of the quantity declaration."""
from __future__ import annotations

import re

from ..services.normalize import units_table
from .base import NEEDS_VERIFICATION, NON_COMPLIANT, PASS, CheckSpec, Rule, RuleContext

REF = "Legal Metrology (Packaged Commodities) Rules, 2011 - Rules 11 & 12"
T = "Quantity declaration - value and units"


class Rule11_12(Rule):
    rule_no = "11/12"
    title = T
    checks = [
        CheckSpec("R11_VALUE_UNIT", "11/12", T, "Numeric value with a unit", REF, "HIGH",
                  "All retail packages", ["net_quantity"],
                  "The net quantity has a positive numeric value followed by a recognised unit."),
        CheckSpec("R11_STANDARD_UNIT", "11/12", T, "Standard unit symbols", REF, "MEDIUM",
                  "All retail packages", ["net_quantity"],
                  "The unit is one of the standard symbols/names configured in units.json (e.g. g, kg, mL, L, cm, m, N, "
                  "pieces). Non-standard spellings such as 'gms', 'kgs', 'ltrs' are non-compliant."),
        CheckSpec("R12_QUALIFIER", "11/12", T, "No non-standard qualifying expressions", REF, "HIGH",
                  "All retail packages", ["net_quantity"],
                  "The quantity declaration is not qualified by expressions such as 'approx.', 'about', 'minimum', "
                  "'when packed' (list configured in units.json)."),
    ]

    def evaluate(self, ctx: RuleContext):
        q = ctx.field("net_quantity")
        out = []
        ev = ctx.evidence("net_quantity")
        s1, s2, s3 = self.checks
        if not q.found or q.normalized.get("unparsed"):
            reason = "Net quantity declaration not extracted." if not q.found else (q.note or "Quantity not parsable.")
            if q.found and q.status == "DETECTED" and ctx.coverage_is_conclusive():
                out.append(s1.result(NON_COMPLIANT, "A net quantity label is present but no numeric value with a unit "
                                     "follows it.", ev, "Declare the quantity as a number followed by a standard unit."))
            else:
                out.append(s1.result(NEEDS_VERIFICATION, reason, ev))
            out.append(s2.result(NEEDS_VERIFICATION, "Unit cannot be assessed: " + reason, ev))
            out.append(s3.result(NEEDS_VERIFICATION, "Qualifying expressions cannot be assessed: " + reason, ev))
            return out

        n = q.normalized
        if n.get("value", 0) > 0:
            out.append(s1.result(PASS, f"Quantity {n['value']:g} with unit '{n['unit_raw']}' ({n['dimension']}).", ev))
        else:
            out.append(s1.result(NON_COMPLIANT, "Declared quantity value is zero or invalid.", ev,
                                 "Declare a positive net quantity."))

        if n.get("standard_unit"):
            out.append(s2.result(PASS, f"Unit '{n['unit_raw']}' is a standard unit ({n['unit_symbol']}).", ev))
        elif q.status == "DETECTED":
            out.append(s2.result(NON_COMPLIANT, f"Non-standard unit '{n['unit_raw']}' used; the standard symbol is "
                                 f"'{n['unit_symbol']}'.", ev, f"Use the standard unit symbol '{n['unit_symbol']}'."))
        else:
            out.append(s2.result(NEEDS_VERIFICATION, f"Unit read as '{n['unit_raw']}' (non-standard) with low OCR "
                                 "confidence.", ev, "Verify the unit symbol printed on the package."))

        quals = units_table().get("qualifying_expressions", [])
        text = q.evidence.lower()
        found = n.get("qualifier") or next((w for w in quals if re.search(rf"(?<!\w){re.escape(w)}(?!\w)", text)), None)
        if found:
            out.append(s3.result(NON_COMPLIANT, f"Quantity declaration is qualified by the expression '{found}'.", ev,
                                 "Remove qualifying expressions; declare the exact net quantity."))
        else:
            out.append(s3.result(PASS, "No qualifying expression found in the quantity declaration.", ev))
        return out
