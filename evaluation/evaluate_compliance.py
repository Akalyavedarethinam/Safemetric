"""
Compliance-analysis evaluation (Module 4) on the synthetic test images.

Every synthetic record carries the labelling defects that were injected on purpose (missing declarations,
"approx." qualifiers, non-standard units, tax-exclusive MRP wording, conflicting MRPs, wrong unit sale price).
For each test image we run the SAME rule engine the application uses on

  oracle  - the ground-truth text of the image (perfect OCR)      -> what the rules can detect at all
  ocr     - the saved OCR output of the image (evaluate_ocr.py)   -> what the full system detects

and report, per defect type, how often the expected check was raised as a potential finding
(NON_COMPLIANT or NEEDS_VERIFICATION), plus false NON_COMPLIANT findings on defect-free labels.
These are synthetic checks of the software, not a validation of legal conclusions.

    python evaluation/evaluate_compliance.py --ocr-tag hybrid_auto --split test
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "evaluation"))

from evaluate_extraction import pseudo_lines  # noqa: E402

# injected defect -> (check id, fields that must be visible for the defect to be observable, type)
DEFECT_CHECK = {
    "qualifier": ("R12_QUALIFIER", ["net_quantity"], "present"),
    "nonstandard_unit": ("R11_STANDARD_UNIT", ["net_quantity"], "present"),
    "tax_exclusive_wording": ("R6_MRP_TAXES", ["mrp"], "present"),
    "conflicting_mrp": ("R6_MRP", ["mrp", "mrp_conflict"], "present"),
    "wrong_unit_sale_price": ("R6_USP", ["unit_sale_price", "mrp", "net_quantity"], "present"),
    "missing:mrp": ("R6_MRP", [], "missing"),
    "missing:net_quantity": ("R6_NET_QUANTITY", [], "missing"),
    "missing:date": ("R6_DATE", [], "missing"),
    "missing:manufacturer": ("R6_MANUFACTURER", [], "missing"),
    "missing:customer_care": ("R6_CONSUMER_CARE", [], "missing"),
    "missing:expiry": ("R6_BEST_BEFORE", [], "missing"),
    "missing:unit_sale_price": ("R6_USP", [], "missing"),
    "no_tax_inclusive_statement": ("R6_MRP_TAXES", ["mrp"], "present"),
}
FULL_LAYOUTS = {"full_label", "two_panel", "table", "centered"}
INSPECTION_DATE = datetime(2026, 10, 1)


def jl(p):
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            yield json.loads(line)


LEGACY_ABSENCE = False


def run_rules(images_ocr, category, imported, all_panels, quality_status="GOOD"):
    from app.rules.base import ImageInfo, RuleContext, category_config, load_config
    from app.rules.registry import aggregate, run_rules as rr
    from app.services import extraction
    fields = extraction.extract_fields(images_ocr, "")
    infos = []
    for im in images_ocr:
        confs = [l["confidence"] for l in im["merged"]] or [0.0]
        infos.append(ImageInfo(id=im["image_id"], name=im["image_name"], side=im["side"], quality_status=quality_status,
                               width=1000, height=1400, panel_width_mm=None, panel_height_mm=None,
                               mean_confidence=sum(confs) / len(confs), lines=im["merged"]))
    common = load_config("common_rules.json")
    if LEGACY_ABSENCE:     # v2.1 behaviour: absence becomes NON_COMPLIANT when coverage looks conclusive
        common = {**common, "missing_declaration": {**common["missing_declaration"], "allow_non_compliant_from_ocr_absence": True}}
    ctx = RuleContext(category=category, is_imported=imported, registration_number="", all_panels_captured=all_panels,
                      inspection_date=INSPECTION_DATE, product_name="", fields=fields, images=infos,
                      category_cfg=category_config(category), common=common)
    findings = rr(ctx)
    return {f["check_id"]: f["status"] for f in findings}, aggregate(findings)["overall_status"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test")
    ap.add_argument("--ocr-tag", default="hybrid_auto")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--assume-partial-coverage", action="store_true",
                    help="never tell the rules that all panels were photographed (absence can never be conclusive)")
    ap.add_argument("--legacy-absence-policy", action="store_true",
                    help="evaluate the v2.1 policy (absence can be NON_COMPLIANT) for comparison")
    a = ap.parse_args()
    global LEGACY_ABSENCE
    LEGACY_ABSENCE = a.legacy_absence_policy
    anns = {x["image"]: x for x in jl(ROOT / "datasets" / "ocr_annotations" / f"{a.split}.jsonl")}
    preds = list(jl(ROOT / "evaluation" / "results" / "predictions" / f"ocr_{a.ocr_tag}_{a.split}.jsonl"))
    if a.limit:
        preds = preds[:a.limit]
    stats = {m: defaultdict(Counter) for m in ("oracle", "ocr")}
    false_nc = {m: Counter() for m in ("oracle", "ocr")}
    clean_images = 0
    agree = Counter()
    quality_counts = Counter()
    for p in preds:
        ann = anns[p["image"]]
        all_panels = ann["layout"] in FULL_LAYOUTS and "partial_visibility" not in ann["conditions"]
        rules_all_panels = all_panels and not a.assume_partial_coverage
        visible_fields = {f for l in ann["lines"] if l["visible"] and not l["partial"] and l["legible"] for f in l["fields"]}
        gt_lines = [{"text": l["text"], "size": l["size"]} for l in ann["lines"] if l["visible"] and l["text"]]
        oracle_imgs = [{"image_id": 1, "image_name": "gt", "side": "front",
                        "passes": [{"lines": pseudo_lines(gt_lines)}], "merged": pseudo_lines(gt_lines)}]
        ocr_imgs = [{"image_id": 1, "image_name": "ocr", "side": "front",
                     "passes": [{"lines": x["lines"]} for x in p["passes"]], "merged": p["lines"]}]
        # the application grades every photo before OCR; a POOR photo can never make an absence conclusive
        from app.services import preprocess, quality
        q = quality.assess_quality(preprocess.load_image((ROOT / "datasets" / p["image"]).read_bytes()))["status"]
        res = {"oracle": run_rules(oracle_imgs, ann["app_category"], ann["imported"], rules_all_panels),
               "ocr": run_rules(ocr_imgs, ann["app_category"], ann["imported"], rules_all_panels, q)}
        quality_counts[q] += 1
        observable = []
        for d in ann["defects"]:
            if d not in DEFECT_CHECK:
                continue
            check, need, kind = DEFECT_CHECK[d]
            if kind == "present" and not all(f in visible_fields for f in need[:1]):
                continue                      # the defective declaration is not visible in this photo
            if kind == "missing" and not all_panels:
                continue                      # absence is only observable when the whole label is photographed
            observable.append((d, check))
        for mode, (checks, overall) in res.items():
            for d, check in observable:
                st = checks.get(check, "ABSENT")
                s = stats[mode][d]
                s["n"] += 1
                s["flagged"] += st in ("NON_COMPLIANT", "NEEDS_VERIFICATION")
                s["non_compliant"] += st == "NON_COMPLIANT"
        if not ann["defects"] and all_panels and "partial_visibility" not in ann["conditions"]:
            clean_images += 1
            for mode, (checks, overall) in res.items():
                for c, st in checks.items():
                    if st == "NON_COMPLIANT":
                        false_nc[mode][c] += 1
                false_nc[mode]["__any__"] += any(st == "NON_COMPLIANT" for st in checks.values())
        oc, oo = res["oracle"][0], res["ocr"][0]
        for c in oc:
            agree["n"] += 1
            agree["same"] += oc[c] == oo.get(c)

    def table(mode):
        out = {}
        for d, s in sorted(stats[mode].items()):
            out[d] = {"check": DEFECT_CHECK[d][0], "observable_cases": s["n"],
                      "flagged_rate": round(s["flagged"] / s["n"], 4) if s["n"] else None,
                      "non_compliant_rate": round(s["non_compliant"] / s["n"], 4) if s["n"] else None}
        tot = sum(s["n"] for s in stats[mode].values())
        flg = sum(s["flagged"] for s in stats[mode].values())
        return {"per_defect": out, "overall_flagged_rate": round(flg / tot, 4) if tot else None, "observable_defects": tot,
                "clean_full_labels": clean_images,
                "false_non_compliant_rate_any": round(false_nc[mode]["__any__"] / clean_images, 4) if clean_images else None,
                "false_non_compliant_by_check": {k: v for k, v in false_nc[mode].most_common() if k != "__any__"}}
    out = {"split": a.split, "ocr_tag": a.ocr_tag, "images": len(preds), "oracle": table("oracle"), "ocr": table("ocr"),
           "status_agreement_ocr_vs_oracle": round(agree["same"] / agree["n"], 4) if agree["n"] else None,
           "image_quality_grades": dict(quality_counts),
           "note": "Synthetic defects; findings are potential findings requiring verification, not legal judgements."}
    out["absence_policy"] = "v2.1 (absence can be NON_COMPLIANT)" if a.legacy_absence_policy else "v2.2 (absence = needs verification)"
    path = ROOT / "evaluation" / "results" / f"compliance_{a.ocr_tag}{'_v21policy' if a.legacy_absence_policy else ''}_{a.split}.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    for m in ("oracle", "ocr"):
        t = out[m]
        print(f"[{m}] defects flagged {t['overall_flagged_rate']} of {t['observable_defects']}; false NON_COMPLIANT on "
              f"{t['clean_full_labels']} clean labels: {t['false_non_compliant_rate_any']}")
        for d, v in t["per_defect"].items():
            print(f"   {d:24s} {v['check']:18s} n={v['observable_cases']:3d} flagged={v['flagged_rate']} NC={v['non_compliant_rate']}")
        print("   false NC by check:", t["false_non_compliant_by_check"])
    print("status agreement OCR vs oracle:", out["status_agreement_ocr_vs_oracle"])


if __name__ == "__main__":
    main()
