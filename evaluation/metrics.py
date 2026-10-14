"""
Field-level comparison rules and precision / recall / F1 bookkeeping for structured extraction.

A field counts as CORRECT when the prediction matches the ground truth under the field's rule below.
    TP  prediction present and correct
    FP  prediction present but wrong, or present although the field is not on the label
    FN  field on the label but missing or wrong      (a wrong value is both an FP and an FN)
Field accuracy counts "both absent" as correct; document exact match = every scored field correct.
"""
from __future__ import annotations

import re
from collections import defaultdict

FIELDS = ["product_name", "brand_name", "net_quantity", "mrp", "mfg_date", "packed_on", "expiry_date", "best_before",
          "batch_number", "manufacturer_name", "manufacturer_address", "customer_care", "fssai_license",
          "country_of_origin", "importer", "unit_sale_price"]

UNIT_CANON = {"g": "g", "gm": "g", "gms": "g", "kg": "kg", "kgs": "kg", "ml": "ml", "mls": "ml", "l": "L", "ltr": "L",
              "ltrs": "L", "litre": "L", "n": "N", "u": "N", "pcs": "N", "pieces": "N", "sheets": "sheets",
              "pairs": "pairs", "pair": "pairs", "m": "m", "metre": "m"}
FACTOR = {"g": 1, "kg": 1000, "ml": 1, "L": 1000}


def _alnum(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _qty(s: str):
    m = re.match(r"^\s*([\d.]+)\s*(\S+)\s*$", s or "")
    if not m:
        return None
    try:
        v = float(m.group(1))
    except ValueError:
        return None
    u = UNIT_CANON.get(m.group(2).lower().strip("."), m.group(2))
    return v * FACTOR.get(u, 1), {"g": "g", "kg": "g", "ml": "ml", "L": "ml"}.get(u, u)


def _tokens(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (s or "").lower())


def _token_f1(a: str, b: str) -> float:
    from collections import Counter
    ca, cb = Counter(_tokens(a)), Counter(_tokens(b))
    common = sum((ca & cb).values())
    if not common:
        return 0.0
    p, r = common / sum(cb.values()), common / sum(ca.values())
    return 2 * p * r / (p + r)


def _phone_or_email(x: str) -> str:
    x = x.strip().lower()
    if "@" in x:
        return x.replace(" ", "")
    d = re.sub(r"\D", "", x)
    return d[-10:]


def _duration(s: str):
    m = re.match(r"^\s*(\d+)\s*(day|month|year)s?\s*$", (s or "").lower())
    return (int(m.group(1)), m.group(2)) if m else None


def match(field: str, gt: str, pred: str) -> bool:
    if not pred:
        return False
    if field in ("product_name", "brand_name", "manufacturer_name", "importer", "country_of_origin"):
        return _alnum(gt) == _alnum(pred)
    if field == "manufacturer_address":
        return _token_f1(gt, pred) >= 0.8
    if field == "net_quantity":
        a, b = _qty(gt), _qty(pred)
        return a is not None and b is not None and abs(a[0] - b[0]) < 1e-6 and a[1] == b[1]
    if field == "mrp":
        try:
            return abs(float(gt) - float(pred)) < 0.005
        except ValueError:
            return False
    if field in ("mfg_date", "packed_on", "expiry_date", "best_before"):
        dg, dp = _duration(gt), _duration(pred)
        if dg or dp:
            return dg == dp
        return gt.strip() == pred.strip()
    if field == "batch_number":
        return re.sub(r"[^A-Z0-9]", "", gt.upper()) == re.sub(r"[^A-Z0-9]", "", pred.upper())
    if field == "fssai_license":
        return re.sub(r"\D", "", gt) == re.sub(r"\D", "", pred)
    if field == "customer_care":
        g = {_phone_or_email(x) for x in gt.split(";") if x.strip()}
        p = {_phone_or_email(x) for x in pred.split(";") if x.strip()}
        return bool(g & p)
    if field == "unit_sale_price":
        mg = re.match(r"([\d.]+)\s*per\s*(?:1\s*)?(\S+)", gt)
        mp = re.match(r"([\d.]+)\s*per\s*(?:1\s*)?(\S+)", pred)
        if not mg or not mp:
            return False
        ug = UNIT_CANON.get(mg.group(2).lower(), mg.group(2))
        up = UNIT_CANON.get(mp.group(2).lower(), mp.group(2))
        return abs(float(mg.group(1)) - float(mp.group(1))) < 0.011 and ug == up
    return _alnum(gt) == _alnum(pred)


class Scorer:
    def __init__(self, fields=FIELDS):
        self.fields = list(fields)
        self.c = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "correct": 0, "n": 0, "gt": 0})
        self.docs = 0
        self.docs_exact = 0
        self.errors = defaultdict(list)

    def add(self, expected: dict, predicted: dict, ignore: set | None = None, example_id: str = ""):
        ignore = ignore or set()
        all_ok = True
        for f in self.fields:
            if f in ignore:
                continue
            g, p = expected.get(f, ""), predicted.get(f, "")
            c = self.c[f]
            c["n"] += 1
            ok = match(f, g, p) if g else not p
            if g:
                c["gt"] += 1
            if g and p and ok:
                c["tp"] += 1
            else:
                if p:
                    c["fp"] += 1
                if g:
                    c["fn"] += 1
            c["correct"] += ok
            if not ok:
                all_ok = False
                if len(self.errors[f]) < 25:
                    self.errors[f].append({"id": example_id, "expected": g, "predicted": p})
        self.docs += 1
        self.docs_exact += all_ok

    def summary(self) -> dict:
        per = {}
        TP = FP = FN = 0
        for f in self.fields:
            c = self.c[f]
            tp, fp, fn = c["tp"], c["fp"], c["fn"]
            TP, FP, FN = TP + tp, FP + fp, FN + fn
            P = tp / (tp + fp) if tp + fp else 0.0
            R = tp / (tp + fn) if tp + fn else 0.0
            per[f] = {"precision": round(P, 4), "recall": round(R, 4), "f1": round(2 * P * R / (P + R), 4) if P + R else 0.0,
                      "accuracy": round(c["correct"] / c["n"], 4) if c["n"] else 0.0, "support": c["gt"]}
        P = TP / (TP + FP) if TP + FP else 0.0
        R = TP / (TP + FN) if TP + FN else 0.0
        macro = [v["f1"] for v in per.values() if v["support"]]
        return {"micro_precision": round(P, 4), "micro_recall": round(R, 4),
                "micro_f1": round(2 * P * R / (P + R), 4) if P + R else 0.0,
                "macro_f1": round(sum(macro) / len(macro), 4) if macro else 0.0,
                "document_exact_match": round(self.docs_exact / self.docs, 4) if self.docs else 0.0,
                "documents": self.docs, "per_field": per}
