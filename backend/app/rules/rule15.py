"""
Rule 15 - Additional declarations for specific commodities / packages.

The required declarations are NOT hard-coded: they are read from
rules/config/<category>_rules.json -> "additional_declarations". Adding a new commodity
category is a matter of adding a JSON file.
"""
from __future__ import annotations

from .base import NEEDS_VERIFICATION, NOT_APPLICABLE, PASS, CheckSpec, Rule, RuleContext

REF = "Legal Metrology (Packaged Commodities) Rules, 2011 - Rule 15 (commodity-specific declarations)"
T = "Specific commodity / package declarations"


class Rule15(Rule):
    rule_no = "15"
    title = T
    checks = [CheckSpec(
        "R15_SPECIFIC", "15", T, "Category-specific additional declarations", REF, "MEDIUM",
        "Only for categories whose configuration lists additional declarations",
        ["category configuration"],
        "Each configured additional declaration for the selected category is detected on the package. A missing "
        "declaration is NEEDS_VERIFICATION (these requirements often come from other statutes).",
        "Verify commodity-specific declarations against the applicable regulation.")]

    def evaluate(self, ctx: RuleContext):
        base = self.checks[0]
        items = ctx.category_cfg.get("additional_declarations") or []
        if not items:
            return [base.result(NOT_APPLICABLE, f"No additional declarations configured for the "
                                f"'{ctx.category_cfg['label']}' category.", applicable=False)]
        out = []
        for item in items:
            spec = CheckSpec(f"R15_{item['id'].upper()}", "15", T, item["title"], item.get("source", REF),
                             item.get("severity", "MEDIUM"), f"Category: {ctx.category_cfg['label']}", [item["field"]],
                             f"'{item['title']}' is detected on the package.", base.verification)
            f = ctx.field(item["field"])
            if f and f.found and f.status in ("DETECTED", "LOW_CONFIDENCE"):
                out.append(spec.result(PASS, f"{item['title']} detected: {f.value[:80]}.", ctx.evidence(item["field"])))
            elif f and f.found:
                out.append(spec.result(NEEDS_VERIFICATION, f"{item['title']} read with low confidence.",
                                       ctx.evidence(item["field"]), f"Verify the {item['title'].lower()}."))
            else:
                out.append(spec.result(NEEDS_VERIFICATION, f"{item['title']} was not detected in the uploaded images "
                                       f"(source: {item.get('source', 'category configuration')}).",
                                       recommendation=f"Verify whether the {item['title'].lower()} is required and printed."))
        return out

    def dynamic_specs(self) -> list[CheckSpec]:
        """All possible category-specific checks (for the rules catalogue page)."""
        from .base import CONFIG_DIR, load_config
        seen, out = set(), []
        for p in sorted(CONFIG_DIR.glob("*_rules.json")):
            if p.name == "common_rules.json":
                continue
            cfg = load_config(p.name)
            for item in cfg.get("additional_declarations", []):
                cid = f"R15_{item['id'].upper()}"
                if cid in seen:
                    continue
                seen.add(cid)
                out.append(CheckSpec(cid, "15", T, item["title"], item.get("source", REF), item.get("severity", "MEDIUM"),
                                     "Categories: " + ", ".join(
                                         load_config(q.name)["label"] for q in sorted(CONFIG_DIR.glob("*_rules.json"))
                                         if q.name != "common_rules.json" and any(
                                             i["id"] == item["id"] for i in load_config(q.name).get("additional_declarations", []))),
                                     [item["field"]], f"'{item['title']}' is detected on the package.",
                                     self.checks[0].verification))
        return out
