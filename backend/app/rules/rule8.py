"""Rule 8 - Principal display panel: placement, grouping and spacing of declarations."""
from __future__ import annotations

from .base import NEEDS_VERIFICATION, NON_COMPLIANT, PASS, CheckSpec, Rule, RuleContext

REF = "Legal Metrology (Packaged Commodities) Rules, 2011 - Rule 8"
T = "Principal display panel - placement and spacing"


class Rule8(Rule):
    rule_no = "8"
    title = T
    checks = [
        CheckSpec("R8_PDP_IMAGE", "8", T, "Principal display panel photographed", REF, "LOW",
                  "All retail packages", ["image side designation"],
                  "At least one uploaded image is designated as the FRONT (principal display panel).",
                  "Photograph the panel most likely to be displayed to the consumer and mark it as Front."),
        CheckSpec("R8_NET_QTY_ON_PDP", "8", T, "Net quantity shown on the principal display panel", REF, "HIGH",
                  "All retail packages", ["net_quantity", "image side designation"],
                  "The net quantity declaration is located on an image designated FRONT.",
                  "Confirm on the physical package that the net quantity is on the principal display panel."),
        CheckSpec("R8_SPACING", "8", T, "Spacing, grouping and physical placement of declarations", REF, "MEDIUM",
                  "All retail packages", ["physical package"],
                  "Spacing/clear-space and physical placement requirements cannot be reliably measured from photographs.",
                  "Inspect the physical package for spacing and placement requirements."),
    ]

    def evaluate(self, ctx: RuleContext):
        out = []
        fronts = [i for i in ctx.images if i.side == "front"]
        s = self.spec("R8_PDP_IMAGE")
        if fronts:
            out.append(s.result(PASS, f"{len(fronts)} image(s) designated as the principal display panel (front)."))
        else:
            out.append(s.result(NEEDS_VERIFICATION, "No image was designated as the Front / principal display panel.",
                                recommendation="Upload a photograph of the principal display panel and mark it as Front."))

        s = self.spec("R8_NET_QTY_ON_PDP")
        q = ctx.field("net_quantity")
        on_front = q.found and q.source_side == "front"
        also_front = any(a.get("side") == "front" for a in q.alternatives) if q.found else False
        if on_front or also_front:
            out.append(s.result(PASS, "Net quantity declaration located on the principal display panel (front image).",
                                ctx.evidence("net_quantity")))
        elif not q.found:
            out.append(s.result(NEEDS_VERIFICATION, "Net quantity declaration not extracted, placement cannot be assessed."))
        elif not fronts:
            out.append(s.result(NEEDS_VERIFICATION, f"Net quantity found on the '{q.source_side}' panel; no front panel "
                                "was designated.", ctx.evidence("net_quantity")))
        elif ctx.coverage_is_conclusive():
            out.append(s.result(NON_COMPLIANT, f"Net quantity is declared only on the '{q.source_side}' panel and not on "
                                "the designated principal display panel.", ctx.evidence("net_quantity"),
                                "Print the net quantity declaration on the principal display panel."))
        else:
            out.append(s.result(NEEDS_VERIFICATION, f"Net quantity found on the '{q.source_side}' panel only; it was not "
                                "read on the front image.", ctx.evidence("net_quantity"),
                                "Confirm whether the net quantity appears on the principal display panel."))

        s = self.spec("R8_SPACING")
        declared_sides = sorted({f.source_side for f in ctx.fields.values() if f.found and f.source_side})
        out.append(s.result(NEEDS_VERIFICATION,
                            "Clear-space, grouping and physical placement requirements cannot be verified reliably from "
                            f"photographs. Declarations were detected on: {', '.join(declared_sides) or 'no panel'}.",
                            ctx.evidence("net_quantity", "mrp")))
        return out
