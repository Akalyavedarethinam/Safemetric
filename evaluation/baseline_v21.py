"""
Score the ORIGINAL v2.1 extraction code (as uploaded, before this upgrade) on saved OCR predictions, so the
end-to-end improvement can be measured on exactly the same test photos.

    python evaluation/baseline_v21.py --orig-backend /path/to/v2.1/safemetric/backend \
        --ocr-tag tesseract_original --split test

v2.1 had no brand / product-name fields and one combined date field per kind, so its output is mapped to the
structured keys like this: the "mfg_date" field goes to mfg_date or packed_on according to its printed label, and
the "best_before" field goes to best_before or expiry_date the same way.
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def jl(p):
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            yield json.loads(line)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--orig-backend", required=True)
    ap.add_argument("--ocr-tag", default="tesseract_original")
    ap.add_argument("--split", default="test")
    a = ap.parse_args()
    sys.path.insert(0, str(Path(a.orig_backend).resolve()))
    ext = importlib.import_module("app.services.extraction")            # the v2.1 module
    assert not hasattr(ext, "_role_candidates"), "this is not the v2.1 extraction module"
    sys.path.insert(0, str(ROOT / "evaluation"))
    from metrics import Scorer                                           # noqa: E402
    sys.path.pop(0)
    # the v2.2 structured helpers are pure functions; load them by file path to avoid the package clash
    spec = importlib.util.spec_from_file_location("structured_v22", ROOT / "backend/app/services/structured.py")
    st = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(st)

    anns = {x["image"]: x for x in jl(ROOT / "datasets" / "ocr_annotations" / f"{a.split}.jsonl")}
    sc, by = Scorer(), defaultdict(Scorer)
    for r in jl(ROOT / "evaluation" / "results" / "predictions" / f"ocr_{a.ocr_tag}_{a.split}.jsonl"):
        ann = anns[r["image"]]
        imgs = [{"image_id": 1, "image_name": "x", "side": "front", "passes": [{"lines": p["lines"]} for p in r["passes"]],
                 "merged": r["lines"]}]
        try:
            f = ext.extract_fields(imgs, "")
        except Exception:
            f = {}
        pred = {}

        def found(k):
            x = f.get(k)
            return x if x is not None and x.found else None
        q = found("net_quantity")
        if q and q.normalized.get("value") is not None:
            pred["net_quantity"] = f"{st._num(float(q.normalized['value']))} {st.canon_unit(q.normalized.get('unit_raw', ''))}"
        m = found("mrp")
        if m and m.normalized.get("amount") is not None:
            pred["mrp"] = f"{float(m.normalized['amount']):.2f}"
        d = found("mfg_date")
        if d and d.value:
            v = st._date_value(d)
            lab = str(d.normalized.get("label", ""))
            pred["packed_on" if re.search(r"pack|pkd|pkg", lab, re.I) else "mfg_date"] = v
        b = found("best_before")
        if b and b.value:
            v = st._date_value(b)
            lab = str(b.normalized.get("label", ""))
            pred["best_before" if (re.search(r"best|bb", lab, re.I) or b.normalized.get("type") == "duration")
                 else "expiry_date"] = v
        for k in ("batch_number", "fssai_license", "country_of_origin"):
            x = found(k)
            if x and x.value:
                pred[k] = re.sub(r"\D", "", x.value) if k == "fssai_license" else x.value
        mp = found("manufacturer_packer")
        if mp:
            name, addr = st.split_name_address(mp.normalized.get("address") or mp.value, mp.normalized.get("name", ""))
            pred["manufacturer_name"], pred["manufacturer_address"] = name, addr
        c = found("consumer_care")
        if c:
            contacts = [st.phone_digits(x) for x in c.normalized.get("phones", [])] + [e.lower() for e in c.normalized.get("emails", [])]
            if contacts:
                pred["customer_care"] = "; ".join(contacts)
        im = found("importer")
        if im:
            pred["importer"] = st.split_name_address(im.normalized.get("address") or im.value, im.normalized.get("name", ""))[0]
        u = found("unit_sale_price")
        if u and u.normalized.get("amount") is not None:
            pred["unit_sale_price"] = f"{float(u.normalized['amount']):.2f} per {st.canon_unit(u.normalized.get('unit_symbol', ''))}"
        pred = {k: v for k, v in pred.items() if v}
        ignore = set(ann.get("fields_not_fully_visible", []))
        sc.add(ann["expected_fields"], pred, ignore, r["image"])
        for cnd in ann["conditions"]:
            by[cnd].add(ann["expected_fields"], pred, ignore, r["image"])
    s = sc.summary()
    out = {"mode": "ocr", "split": a.split, "roles": "none (v2.1)", "ocr_tag": a.ocr_tag, "overall": s,
           "groups": {k: {kk: vv for kk, vv in v.summary().items() if kk != "per_field"} for k, v in sorted(by.items())},
           "errors": {k: v[:15] for k, v in sc.errors.items()}}
    p = ROOT / "evaluation" / "results" / f"extraction_ocr_{a.ocr_tag}_v21original_{a.split}.json"
    p.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"v2.1 original extraction on {a.ocr_tag}: micro P/R/F1 = {s['micro_precision']:.3f}/{s['micro_recall']:.3f}/"
          f"{s['micro_f1']:.3f}  doc exact = {s['document_exact_match']:.3f}")
    for k, v in s["per_field"].items():
        print(f"  {k:22s} F1={v['f1']:.3f} n={v['support']}")


if __name__ == "__main__":
    main()
