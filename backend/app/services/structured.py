"""
Flat, user-facing structured output built from the extracted FieldResults.

    {"product_name": "SUNRISE RICE", "brand_name": "...", "net_quantity": "5 kg", "mrp": "650.00",
     "mfg_date": "08/2026", "packed_on": "09/2026", "expiry_date": "", "best_before": "6 months",
     "batch_number": "SR0926A", "manufacturer_name": "...", "manufacturer_address": "...",
     "customer_care": "18001234567; care@x.in", "fssai_license": "...", "country_of_origin": "India",
     "importer": "", "unit_sale_price": "0.13 per g"}

Values are normalised (numbers without currency symbols, canonical units, MM/YYYY or DD/MM/YYYY dates).
Fields that were not found are omitted. `structured_detail` adds confidence, status and evidence per field.
"""
from __future__ import annotations

import re

UNIT_CANON = {
    "g": "g", "gm": "g", "gms": "g", "gram": "g", "grams": "g", "grm": "g", "grms": "g",
    "kg": "kg", "kgs": "kg", "kilogram": "kg", "kilograms": "kg", "kilo": "kg",
    "mg": "mg", "ml": "ml", "mls": "ml", "millilitre": "ml", "cc": "ml",
    "l": "L", "ltr": "L", "ltrs": "L", "litre": "L", "litres": "L", "liter": "L", "liters": "L", "lt": "L", "lts": "L",
    "n": "N", "u": "N", "unit": "N", "units": "N", "pcs": "N", "pc": "N", "piece": "N", "pieces": "N", "nos": "N",
    "no": "N", "count": "N", "tablets": "N", "sheets": "sheets", "pairs": "pairs", "pair": "pairs",
    "m": "m", "metre": "m", "metres": "m", "meter": "m", "meters": "m", "mtr": "m", "mtrs": "m", "cm": "cm", "mm": "mm",
}
STRUCTURED_FIELDS = ["product_name", "brand_name", "net_quantity", "mrp", "mfg_date", "packed_on", "expiry_date",
                     "best_before", "batch_number", "manufacturer_name", "manufacturer_address", "customer_care",
                     "fssai_license", "country_of_origin", "importer", "unit_sale_price"]


def _num(v: float) -> str:
    return (f"{v:.3f}".rstrip("0").rstrip(".")) if v != int(v) else str(int(v))


def canon_unit(u: str) -> str:
    return UNIT_CANON.get((u or "").strip().strip(".").lower(), (u or "").strip())


def phone_digits(p: str) -> str:
    d = re.sub(r"\D", "", p or "")
    if d.startswith("91") and len(d) >= 12:
        d = d[2:]
    if d.startswith("0") and len(d) == 11:
        d = d[1:]
    return d


def _date_value(fr) -> str:
    if not fr or not fr.found or not fr.value:
        return ""
    n = fr.normalized or {}
    if n.get("type") == "duration":
        unit = n.get("unit", "").rstrip("s")
        unit = {"yr": "year", "yrs": "year"}.get(unit, unit)
        amt = n.get("amount")
        return f"{amt} {unit}{'s' if amt != 1 else ''}"
    if n.get("type") == "date":
        if n.get("day"):
            return f"{n['day']:02d}/{n['month']:02d}/{n['year']}"
        return f"{n['month']:02d}/{n['year']}"
    return ""


def split_name_address(text: str, name: str) -> tuple[str, str]:
    """'ABC Foods Pvt. Ltd., Plot 21, ... - 440016' -> ('ABC Foods Pvt. Ltd.', 'Plot 21, ... - 440016')"""
    # common OCR slips in company suffixes ("Pvt Lid.", "LId.", "Limitied") before splitting
    text = re.sub(r"\bL[iIl1]d\b\.?", "Ltd.", (text or "").strip(" ,"))
    text = re.sub(r"\bLimit[i1l]ed\b", "Limited", text)
    name = (name or "").strip(" ,")
    # company names end at the legal suffix; this also handles "Co., Ltd." style names with commas
    m = re.match(r"^(.*?\b(?:pvt\.?\s*ltd\.?|private\s+limited|ltd\.?|limited|llp|& co\.|co\.,?\s*ltd\.?|s\.p\.a\.|s\.l\.|"
                 r"gmbh|inc\.|sdn\.?\s*bhd\.?|co-operative(?:\s+\w+)*?\s+limited))(?=[\s,]|$)", text, re.I)
    if m and len(m.group(1)) >= 4:
        name = m.group(1).strip(" ,")
    elif not name:
        name = re.split(r",", text, maxsplit=1)[0]
    addr = text[len(name):].strip(" ,") if text.lower().startswith(name.lower()) else text
    return name, addr


def structured_output(fields: dict) -> dict:
    """fields: {name: FieldResult} (from extraction.extract_fields) -> flat dict of normalised strings."""
    f = fields.get
    out: dict[str, str] = {}

    def found(k):
        x = f(k)
        return x if x is not None and x.found and x.status != "NOT_DETECTED" else None

    for k in ("product_name", "brand_name"):
        if found(k) and found(k).value:
            out[k] = found(k).value.strip()
    q = found("net_quantity")
    if q and not q.normalized.get("unparsed") and q.normalized.get("value") is not None:
        out["net_quantity"] = f"{_num(float(q.normalized['value']))} {canon_unit(q.normalized.get('unit_raw', ''))}"
    p = found("mrp")
    if p and p.normalized.get("amount") is not None:
        out["mrp"] = f"{float(p.normalized['amount']):.2f}"
    for key, src in (("mfg_date", "manufacture_date"), ("packed_on", "packed_on"), ("expiry_date", "expiry_date"),
                     ("best_before", "best_before_label")):
        v = _date_value(found(src))
        if v:
            out[key] = v
    b = found("batch_number")
    if b and b.value:
        out["batch_number"] = b.value.strip()
    m = found("manufacturer_packer")
    if m and m.normalized.get("role") == "marketer":
        # a "Marketed by" line is not the manufacturer / packer: use a manufacturer alternative if there is one
        alt = next((a for a in m.alternatives if (a.get("normalized") or {}).get("role") != "marketer"), None)
        m = type("Alt", (), {"normalized": alt["normalized"], "value": alt["value"]})() if alt else None
    if m:
        name, addr = split_name_address(m.normalized.get("address") or m.value, m.normalized.get("name", ""))
        if name:
            out["manufacturer_name"] = name
        if addr:
            out["manufacturer_address"] = addr
    c = found("consumer_care")
    if c:
        contacts = [phone_digits(x) for x in c.normalized.get("phones", [])] + [e.lower() for e in c.normalized.get("emails", [])]
        if contacts:
            out["customer_care"] = "; ".join(dict.fromkeys(contacts))
    fs = found("fssai_license")
    if fs and fs.value:
        out["fssai_license"] = re.sub(r"\D", "", fs.value)
    o = found("country_of_origin")
    if o and o.value:
        out["country_of_origin"] = o.value
    imp = found("importer")
    if imp:
        name, _ = split_name_address(imp.normalized.get("address") or imp.value, imp.normalized.get("name", ""))
        if name:
            out["importer"] = name
    u = found("unit_sale_price")
    if u and u.normalized.get("amount") is not None and not u.normalized.get("unparsed"):
        per = u.normalized.get("per_quantity", 1.0)
        unit = canon_unit(u.normalized.get("unit_symbol", ""))
        out["unit_sale_price"] = f"{float(u.normalized['amount']):.2f} per {'' if per == 1 else _num(per) + ' '}{unit}"
    return out


_SOURCE = {"mfg_date": "manufacture_date", "best_before": "best_before_label", "manufacturer_name": "manufacturer_packer",
           "manufacturer_address": "manufacturer_packer", "customer_care": "consumer_care"}


def structured_detail(fields: dict) -> dict:
    """Structured output + per-field confidence / status / evidence for the UI and reports."""
    flat = structured_output(fields)
    out = {}
    for k in STRUCTURED_FIELDS:
        src = fields.get(_SOURCE.get(k, k))
        out[k] = {"value": flat.get(k, ""), "found": k in flat,
                  "confidence": round(src.confidence, 1) if src is not None and k in flat else 0.0,
                  "status": src.status if src is not None and k in flat else "NOT_DETECTED",
                  "evidence": src.evidence if src is not None and k in flat else "",
                  "source_side": src.source_side if src is not None and k in flat else "",
                  "source_image_id": src.source_image_id if src is not None and k in flat else None,
                  "bbox": src.bbox if src is not None and k in flat else None,
                  "method": (src.normalized or {}).get("method", "rules") if src is not None and k in flat else ""}
    return out
