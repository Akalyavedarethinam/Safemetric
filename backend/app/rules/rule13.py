"""Rule 13 - Quantity declared by weight, measure or number as appropriate to the commodity."""
from __future__ import annotations

from .base import NEEDS_VERIFICATION, PASS, CheckSpec, Rule, RuleContext

REF = "Legal Metrology (Packaged Commodities) Rules, 2011 - Rule 13"
T = "Declaration of quantity by weight, measure or number"


class Rule13(Rule):
    rule_no = "13"
    title = T
    checks = [CheckSpec(
        "R13_BASIS", "13", T, "Quantity basis appropriate to the commodity", REF, "MEDIUM",
        "Categories with a configured quantity basis (see <category>_rules.json)", ["net_quantity", "category"],
        "The dimension of the declared unit (mass / volume / length / area / number) is one of the bases configured "
        "for the selected category. Anything else - or a category without configuration - needs verification.",
        "Confirm the commodity-specific manner of declaration.")]

    def evaluate(self, ctx: RuleContext):
        s = self.checks[0]
        q = ctx.field("net_quantity")
        basis = ctx.category_cfg.get("quantity_basis") or []
        label = ctx.category_cfg["label"]
        if not q.found or q.normalized.get("unparsed"):
            return [s.result(NEEDS_VERIFICATION, "Net quantity not extracted; basis cannot be determined.")]
        dim = q.normalized.get("dimension")
        ev = ctx.evidence("net_quantity")
        if not basis:
            return [s.result(NEEDS_VERIFICATION, f"No quantity basis is configured for the '{label}' category; the "
                             f"declaration by {dim} ('{q.value}') must be verified against the commodity-specific requirement.", ev)]
        if dim in basis:
            return [s.result(PASS, f"Quantity declared by {dim} ('{q.value}'), which is a configured basis for "
                             f"'{label}' ({', '.join(basis)}).", ev)]
        return [s.result(NEEDS_VERIFICATION, f"Quantity declared by {dim} ('{q.value}'), but '{label}' is normally "
                         f"declared by {', '.join(basis)}.", ev, "Confirm the correct basis of quantity declaration.")]
