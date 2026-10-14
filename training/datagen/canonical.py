"""Canonical (flat) ground-truth values shared by the dataset generator and the evaluators."""
from __future__ import annotations

import re

UNIT_CANON = {
    "g": "g", "gm": "g", "gms": "g", "gram": "g", "grams": "g", "grm": "g",
    "kg": "kg", "kgs": "kg", "kilogram": "kg", "kilo": "kg",
    "ml": "ml", "mls": "ml", "millilitre": "ml",
    "l": "L", "ltr": "L", "ltrs": "L", "litre": "L", "litres": "L", "liter": "L", "lt": "L", "lts": "L",
    "n": "N", "u": "N", "unit": "N", "units": "N", "pcs": "N", "pc": "N", "piece": "N", "pieces": "N", "nos": "N", "no": "N",
    "count": "N", "sheets": "sheets", "pairs": "pairs", "pair": "pairs", "m": "m", "metre": "m", "metres": "m", "mtr": "m",
}
# the fields the extraction evaluation scores (the user-facing structured output)
EVAL_FIELDS = ["product_name", "brand_name", "net_quantity", "mrp", "mfg_date", "packed_on", "expiry_date", "best_before",
               "batch_number", "manufacturer_name", "manufacturer_address", "customer_care", "fssai_license",
               "country_of_origin", "importer", "unit_sale_price"]


def canon_unit(u: str) -> str:
    return UNIT_CANON.get(u.strip().strip(".").lower(), u.strip())


def fmt_num(v: float) -> str:
    return (f"{v:.3f}".rstrip("0").rstrip(".")) if v != int(v) else str(int(v))


def expected_flat(F: dict) -> dict:
    """Record `fields` -> the flat structured output an ideal extractor would return."""
    out = {}
    for k in ("product_name", "brand_name", "mfg_date", "packed_on", "expiry_date", "best_before", "batch_number",
              "manufacturer_name", "manufacturer_address", "fssai_license", "country_of_origin", "importer"):
        if k in F:
            out[k] = F[k]
    if "net_quantity" in F:
        q = F["net_quantity"]
        out["net_quantity"] = f"{fmt_num(q['value'])} {canon_unit(q['unit'])}"
    if "mrp" in F:
        out["mrp"] = f"{F['mrp']['amount']:.2f}"
    if "unit_sale_price" in F:
        u = F["unit_sale_price"]
        out["unit_sale_price"] = f"{u['amount']:.2f} per {u['per']}"
    if "customer_care" in F and (F["customer_care"]["phones"] or F["customer_care"]["emails"]):
        out["customer_care"] = "; ".join(F["customer_care"]["phones"] + F["customer_care"]["emails"])
    return out


def norm_text(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())
