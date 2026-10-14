"""
Rule registry and overall-status aggregation.

To add a rule: implement a `Rule` subclass in its own module and append it to RULES.
Administrators can deactivate individual checks (RuleSetting table); deactivated checks are
reported as NOT_APPLICABLE with an explicit reason, never silently dropped.
"""
from __future__ import annotations

import hashlib
import json

from .base import (NEEDS_VERIFICATION, NON_COMPLIANT, NOT_APPLICABLE, PASS, CheckResult, RuleContext,
                   load_config)
from .rule6 import Rule6
from .rule7 import Rule7
from .rule8 import Rule8
from .rule9 import Rule9
from .rule11_12 import Rule11_12
from .rule13 import Rule13
from .rule15 import Rule15
from .rule27 import Rule27
from .section18 import Section18

RULES = [Rule6(), Rule7(), Rule8(), Rule9(), Rule11_12(), Rule13(), Rule15(), Rule27(), Section18()]

COMPLIANT, PARTIALLY_COMPLIANT = "COMPLIANT", "PARTIALLY_COMPLIANT"
OVERALL_LABELS = {COMPLIANT: "Compliant", NON_COMPLIANT: "Non-Compliant", PARTIALLY_COMPLIANT: "Partially Compliant",
                  NEEDS_VERIFICATION: "Needs Verification"}


def catalogue() -> list[dict]:
    """Every check the engine can produce (static + configured category checks)."""
    out = []
    for r in RULES:
        specs = list(r.checks)
        if isinstance(r, Rule15):
            specs += r.dynamic_specs()
        for s in specs:
            d = s.to_dict()
            d["rule_group_title"] = r.title
            out.append(d)
    return out


def run_rules(ctx: RuleContext, inactive: set[str] | None = None) -> list[dict]:
    inactive = inactive or set()
    weights = load_config("common_rules.json")["severity_weights"]
    results: list[dict] = []
    for rule in RULES:
        for res in rule.evaluate(ctx):
            res: CheckResult
            d = res.to_dict(weight=weights.get(res.spec.severity, 1))
            if res.spec.check_id in inactive:
                d.update(status=NOT_APPLICABLE, applicable=False,
                         reason="Check deactivated by an administrator in Settings → Statutory Rules. " + d["reason"])
            results.append(d)
    return results


def aggregate(findings: list[dict]) -> dict:
    scoring = load_config("common_rules.json")["scoring"]
    credit = {PASS: scoring["pass_credit"], NEEDS_VERIFICATION: scoring["needs_verification_credit"],
              NON_COMPLIANT: scoring["non_compliant_credit"]}
    applicable = [f for f in findings if f["status"] != NOT_APPLICABLE]
    earned = sum(f["weight"] * credit[f["status"]] for f in applicable)
    total = sum(f["weight"] for f in applicable)
    counts = {s: sum(1 for f in findings if f["status"] == s) for s in (PASS, NON_COMPLIANT, NEEDS_VERIFICATION, NOT_APPLICABLE)}
    nc_high = [f for f in findings if f["status"] == NON_COMPLIANT and f["severity"] == "HIGH"]
    if nc_high:
        overall, why = NON_COMPLIANT, f"{len(nc_high)} high-severity statutory violation(s) identified."
    elif counts[NON_COMPLIANT]:
        overall, why = PARTIALLY_COMPLIANT, f"{counts[NON_COMPLIANT]} medium/low-severity deviation(s) identified."
    elif counts[NEEDS_VERIFICATION]:
        overall, why = NEEDS_VERIFICATION, (f"No violation established, but {counts[NEEDS_VERIFICATION]} check(s) "
                                            "cannot be decided from the images and require physical/authoritative verification.")
    else:
        overall, why = COMPLIANT, "All applicable checks passed."
    return {
        "overall_status": overall,
        "overall_label": OVERALL_LABELS[overall],
        "overall_reason": why,
        "score": round(earned / total * 100, 1) if total else 0.0,
        "earned_points": round(earned, 2),
        "applicable_points": round(total, 2),
        "counts": counts,
        "formula": scoring["description"],
    }


def recommendations(findings: list[dict]) -> list[dict]:
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    recs = []
    for f in findings:
        if f["status"] not in (NON_COMPLIANT, NEEDS_VERIFICATION) or not (f["recommendation"] or f["verification"]):
            continue
        is_nc = f["status"] == NON_COMPLIANT
        recs.append({
            "type": "RECTIFY_VIOLATION" if is_nc else "VERIFY",
            "check_id": f["check_id"], "rule_no": f["rule_no"], "title": f["title"],
            "urgency": ("HIGH" if f["severity"] == "HIGH" else "MEDIUM") if is_nc else "LOW",
            "action": f["recommendation"] or f["verification"],
            "reference": f["reference"],
        })
    recs.sort(key=lambda r: (r["type"] != "RECTIFY_VIOLATION", order.get(r["urgency"], 3)))
    return recs


def integrity_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
