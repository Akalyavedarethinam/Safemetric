"""
Structured declaration extraction.

Input : OCR lines (per image, per OCR pass) with confidence and bounding boxes.
Output: one FieldResult per declaration field with value, parsed value, confidence,
        source image / side, OCR evidence text, bounding box and status.

Every extractor produces *candidates*; candidates coming from different OCR passes of the
same printed region are clustered, and the best reading wins. Distinct regions with
different values are kept as `alternatives` (used e.g. to detect conflicting MRPs).
Nothing is invented: if no candidate exists the field is NOT_DETECTED.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

import numpy as np

from .normalize import (EMAIL_RE, PHONE_RE, PIN_RE, canonical, find_country, lookup_unit,
                        parse_amount, parse_date, unit_pattern, units_table)

DETECTED, NOT_DETECTED, LOW_CONFIDENCE, NEEDS_VERIFICATION = "DETECTED", "NOT_DETECTED", "LOW_CONFIDENCE", "NEEDS_VERIFICATION"

FIELD_LABELS = {
    "manufacturer_packer": "Manufacturer / Packer",
    "importer": "Importer",
    "generic_name": "Generic / Common Name",
    "net_quantity": "Net Quantity",
    "mrp": "Maximum Retail Price (MRP)",
    "mfg_date": "Month & Year of Manufacture / Packing",
    "best_before": "Best Before / Expiry",
    "consumer_care": "Consumer Care Details",
    "country_of_origin": "Country of Origin",
    "unit_sale_price": "Unit Sale Price",
    # supplementary fields used by category-specific (Rule 15) and registration (Rule 27) checks
    "fssai_license": "FSSAI Licence No.",
    "batch_number": "Batch / Lot No.",
    "ingredients": "Ingredients",
    "nutrition_info": "Nutrition Information",
    "bis_mark": "BIS Registration / Standard Mark",
    "registration_number": "LM Registration No.",
    "size_dimensions": "Size / Dimensions",
    # structured-output fields (v2.2): finer-grained than the statutory fields above
    "brand_name": "Brand Name",
    "product_name": "Product Name",
    "manufacture_date": "Date of Manufacture",
    "packed_on": "Date of Packing",
    "expiry_date": "Expiry / Use By",
    "best_before_label": "Best Before (as printed)",
}
PRIMARY_FIELDS = list(FIELD_LABELS)[:10]


@dataclass
class Candidate:
    field: str
    value: str
    normalized: dict
    confidence: float
    image_id: int
    image_name: str
    side: str
    evidence: str
    bbox: dict
    complete: bool = True          # False = partially read (e.g. name without address)
    note: str = ""


@dataclass
class FieldResult:
    field: str
    label: str
    value: str = ""
    normalized: dict = field(default_factory=dict)
    confidence: float = 0.0
    status: str = NOT_DETECTED
    source_image_id: int | None = None
    source_image: str = ""
    source_side: str = ""
    evidence: str = ""
    bbox: dict | None = None
    alternatives: list = field(default_factory=list)
    note: str = ""

    def to_dict(self):
        return asdict(self)

    @property
    def found(self) -> bool:
        return self.status != NOT_DETECTED


# ------------------------------------------------------------------ helpers
def _union(boxes: list[dict]) -> dict:
    x0 = min(b["x"] for b in boxes); y0 = min(b["y"] for b in boxes)
    x1 = max(b["x"] + b["width"] for b in boxes); y1 = max(b["y"] + b["height"] for b in boxes)
    return {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}


def _words_bbox(line: dict, start_char: int, end_char: int) -> dict:
    """Bounding box of the words of `line` that overlap the character span [start, end)."""
    pos, chosen = 0, []
    for w in line.get("words", []):
        ws, we = pos, pos + len(w["text"])
        if we > start_char and ws < end_char:
            chosen.append(w)
        pos = we + 1
    return _union([w["bbox"] for w in chosen]) if chosen else line["bbox"]


def _words_conf(line: dict, start_char: int, end_char: int) -> float:
    pos, confs = 0, []
    for w in line.get("words", []):
        ws, we = pos, pos + len(w["text"])
        if we > start_char and ws < end_char:
            confs.append(w["confidence"])
        pos = we + 1
    return float(np.mean(confs)) if confs else float(line["confidence"])


def lines_below(lines: list[dict], idx: int, max_lines: int = 4, max_gap_factor: float = 2.6) -> list[dict]:
    """Column-aware continuation: lines under lines[idx] that horizontally overlap it."""
    base = lines[idx]["bbox"]
    out, last_bottom = [], base["y"] + base["height"]
    h = max(base["height"], 8)
    cands = sorted((l for l in lines[idx + 1:] if l["bbox"]["y"] >= base["y"] + 0.6 * h),
                   key=lambda l: l["bbox"]["y"])
    for l in cands:
        b = l["bbox"]
        overlap = min(base["x"] + base["width"], b["x"] + b["width"]) - max(base["x"], b["x"])
        if overlap <= 0 or b["x"] > base["x"] + base["width"] * 0.8:
            continue
        if b["y"] - last_bottom > max_gap_factor * h:
            break
        out.append(l)
        last_bottom = b["y"] + b["height"]
        if len(out) >= max_lines:
            break
    return out


_LABEL_ZERO_RE = re.compile(
    r"\b(?:BEF[O0]RE|N[O0](?=\s*[:.])|L[O0]T|C[O0]NSUMER|[O0]RIGIN|C[O0]UNTRY|CUST[O0]MER|PR[O0]DUCT|"
    r"PR[O0]DUCTI[O0]N|B[O0]TTLED)\b", re.I)


def _ocr_match_text(text: str) -> str:
    """Create a matching-only view for common Tesseract spacing/label confusions.

    The original OCR string remains the evidence.  These repairs are deliberately
    limited to declaration labels so normal product names are not rewritten.
    """
    t = canonical(text)
    # monospace / ink-jet stamps: the letter O read as the digit 0 inside declaration labels ("BEF0RE", "N0:")
    t = _LABEL_ZERO_RE.sub(lambda m: m.group(0).replace("0", "O"), t)
    t = re.sub(r"\bN\s+E\s+T\b", "NET", t, flags=re.I)
    t = re.sub(r"\bW\s*T\b", "WT", t, flags=re.I)
    t = re.sub(r"\bQ\s*T\s*Y\b", "QTY", t, flags=re.I)
    t = re.sub(r"\bV\s*O\s*L\b", "VOL", t, flags=re.I)
    t = re.sub(r"\bM\s+R\s+P\b", "MRP", t, flags=re.I)
    t = re.sub(r"\bU\s*S\s*P\b", "USP", t, flags=re.I)
    t = re.sub(r"\bF\s*S\s*S\s*A\s*I\b", "FSSAI", t, flags=re.I)
    t = re.sub(r"\bB\s*A\s*T\s*C\s*H\b", "BATCH", t, flags=re.I)
    t = re.sub(r"\bL\s*O\s*T\b", "LOT", t, flags=re.I)
    t = re.sub(r"\bM\s*F\s*G\b|\bM\s*F\s*D\b", "MFG", t, flags=re.I)
    t = re.sub(r"\bP\s*K\s*D\b", "PKD", t, flags=re.I)
    t = re.sub(r"\bB\s*E\s*S\s*T\s+B\s*E\s*F\s*O\s*R\s*E\b", "BEST BEFORE", t, flags=re.I)
    t = re.sub(r"\bU\s*S\s*E\s+B\s*Y\b", "USE BY", t, flags=re.I)
    t = re.sub(r"\bC\s*O\s*N\s*S\s*U\s*M\s*E\s*R\s+C\s*A\s*R\s*E\b", "CONSUMER CARE", t, flags=re.I)
    t = re.sub(r"\bC\s*U\s*S\s*T\s*O\s*M\s*E\s*R\s+C\s*A\s*R\s*E\b", "CUSTOMER CARE", t, flags=re.I)
    # OCR commonly inserts spaces inside short units as well as before them.
    for spaced, compact in (
        (r"\bK\s*G\b", "KG"), (r"\bG\s*M\s*S\b", "GMS"),
        (r"\bG\s*M\b", "GM"), (r"\bM\s*L\b", "ML"),
        (r"\bL\s*T\s*R\b", "LTR"), (r"\bL\s*T\b", "LT"),
        # only letter-SPACED forms ("N O S"); a plain "No" / "No." (as in "Batch No.") must stay untouched
        (r"\bN\s+O\s+S\b", "NOS"), (r"\bP\s+C\s+S\b", "PCS"),
    ):
        t = re.sub(spaced, compact, t, flags=re.I)
    t = re.sub(r"(?<=\d)\s+(?=(?:KG|G|GM|GMS|MG|ML|L|LTR|LT|N|NOS?)\b)", "", t, flags=re.I)
    t = re.sub(r"\s*[:;]\s*", ": ", t)
    return t


FIELD_KEYWORDS = re.compile(
    r"\b(m\s*\.?\s*r\s*\.?\s*p|net\s*(?:qty|quantity|wt|weight|vol|volume|content)|best\s*before|use\s*by|"
    r"exp(?:iry)?\b|mfg|mfd|packed\s*on|pkd\s*on|date\s*of|customer\s*care|consumer\s*care|"
    r"country\s*of\s*origin|made\s*in|unit\s*sale|fssai|batch|lot\s*no|imported\s*by|marketed\s*by|"
    r"imported\s*(?:&|and)|importer|toll\s*free|e-?mail|phone|tel\b|ph\s*[:.]|helpline|"
    r"manufactured\s*(?:&|and)?\s*(?:packed|marketed)?\s*by|packed\s*by|for\s*(?:consumer|customer)|ingredients|nutrition)",
    re.I)


# ------------------------------------------------------------------ extractors (one per field)
PARTY_RE = {
    "manufacturer_packer": re.compile(
        r"(?P<label>(?:manufactured|mfd\.?|mfg\.?|manufd\.?)\s*(?:(?:&|and|,)\s*(?:packed|marketed|pkd\.?|[a-z]{4,12}\.?))?\s*by"
        r"|(?:packed|pkd\.?|packaged)\s*(?:(?:&|and)\s*marketed)?\s*by"
        r"|marketed\s*by|mktd\.?\s*by|manufacturer|packer|manufacturer\s*(?:&|and|/)\s*packer)\s*[:\-.]?\s*(?P<rest>.*)$",
        re.I),
    "importer": re.compile(
        r"(?P<label>(?:\bi|\bl|\b)mported\s*(?:(?:&|and)\s*[a-z]{4,13}\.?)?\s*by|importer(?:\s*(?:name|&\s*address))?)\s*[:\-.]?\s*(?P<rest>.*)$",
        re.I),
}


def _extract_party(field_name, lines, i, ctx):
    line = lines[i]
    m = PARTY_RE[field_name].search(line["text"])
    if not m:
        return None
    if field_name == "manufacturer_packer" and re.search(r"import", line["text"], re.I):
        return None
    label_start = m.start("label")
    rest = m.group("rest").strip(" :-")
    parts, used = ([rest] if rest else []), [line]
    for nxt in lines_below(lines, i, 5):
        from .line_roles import COMPANY
        # a keyword inside a company name ("Sunrise Nutrition Foods Pvt. Ltd.") is not the start of a new declaration
        if FIELD_KEYWORDS.search(nxt["text"]) and not PIN_RE.search(nxt["text"]) and \
                not (COMPANY.search(nxt["text"]) and ":" not in nxt["text"]):
            break
        parts.append(nxt["text"])
        used.append(nxt)
        if PIN_RE.search(nxt["text"]) or re.search(r"\bindia\s*\.?$", nxt["text"].strip(), re.I) or \
                (find_country(nxt["text"].split(",")[-1]) and "," in nxt["text"]):
            break
    text = ", ".join(p.strip(" ,") for p in parts if p.strip(" ,"))
    if len(re.sub(r"[^A-Za-z]", "", text)) < 4:
        return None
    pin = PIN_RE.search(text)
    name = re.split(r",|\bplot\b|\bno\.|\b\d", text, maxsplit=1, flags=re.I)[0].strip()
    complete = bool(pin) or len(parts) >= 3
    confs = [_words_conf(line, label_start, len(line["text"]))] + [u["confidence"] for u in used[1:]]
    role = "marketer" if re.match(r"mark|mktd", m.group("label"), re.I) else "importer" if field_name == "importer" else \
        "packer" if re.match(r"pack|pkd", m.group("label"), re.I) else "manufacturer"
    return Candidate(field_name, text, {"name": name, "address": text, "pincode": pin.group(0).replace(" ", "") if pin else None,
                                         "role": role, "label": m.group("label").strip()},
                     float(np.mean(confs)), ctx["image_id"], ctx["image_name"], ctx["side"],
                     " / ".join(u["text"] for u in used), _union([u["bbox"] for u in used]), complete,
                     "" if complete else "Name detected but complete address (PIN code) not found")


QTY_LABEL = r"(?:nett?\s*\.?\s*(?:qty|quantity|qnty|wt|weight|wght|vol|volume|content|contents|mass|count)|\bcontents?\b)\s*\.?"
QUALIFIERS = r"(?:approx\.?|approximately|about|around|min\.?|minimum|nearly|not\s+less\s+than)"


def _qty_regex():
    return re.compile(
        rf"(?P<label>{QTY_LABEL})?\s*[:\-=]?\s*(?:\((?:[a-z\s]+)\)\s*)?(?P<qual>{QUALIFIERS}\s*)?"
        rf"(?P<num>[0-9OoIl]+(?:[.,][0-9Oo]+)?)\s*(?P<unit>{unit_pattern()})\b\.?",
        re.I)


def _extract_net_quantity(lines, i, ctx):
    line = lines[i]
    text = line["text"]
    match = _ocr_match_text(text)
    has_label = re.search(QTY_LABEL, match, re.I)
    candidates_text = [(line, match)]
    if has_label and not _qty_regex().search(match):
        nxt = lines_below(lines, i, 1)
        if nxt:
            candidates_text.append((nxt[0], _ocr_match_text(nxt[0]["text"])))
    for src_line, t in candidates_text:
        for m in _qty_regex().finditer(t):
            if not has_label and not m.group("label"):
                # unlabelled quantity: only accept on principal panel-like text lines ("1 kg")
                if len(t) > 22:
                    continue
            num, repaired = parse_amount(m.group("num"))
            unit = lookup_unit(m.group("unit"))
            if num is None or unit is None:
                continue
            if unit["dimension"] == "number" and not (has_label or m.group("label")):
                continue
            qual = (m.group("qual") or "").strip()
            conf = _words_conf(src_line, m.start("num"), m.end("unit"))
            if repaired:
                conf -= 8
            if not (has_label or m.group("label")):
                conf -= 15
            base = num * unit["factor"]
            value = f"{m.group('num')} {m.group('unit')}"
            ev_line = line if src_line is line else src_line
            bbox = _words_bbox(src_line, m.start(), m.end()) if src_line is line else _union([line["bbox"], src_line["bbox"]])
            return Candidate("net_quantity", value.strip(),
                             {"value": num, "unit_raw": m.group("unit"), "unit_symbol": unit["symbol"],
                              "dimension": unit["dimension"], "standard_unit": unit["standard"], "base_value": base,
                              "qualifier": qual or None, "labelled": bool(has_label or m.group("label")),
                              "ocr_repaired": repaired, "letter_height_px": _numeral_height(src_line, m)},
                             conf, ctx["image_id"], ctx["image_name"], ctx["side"],
                             (line["text"] + (" / " + src_line["text"] if src_line is not line else "")), bbox)
    if has_label:
        # label present but no parsable quantity -> record as unreadable declaration
        return Candidate("net_quantity", text, {"unparsed": True}, line["confidence"] - 20, ctx["image_id"],
                         ctx["image_name"], ctx["side"], text, line["bbox"], False,
                         "Net quantity label found but value/unit could not be parsed")
    return None


def _numeral_height(line: dict, m: re.Match) -> float | None:
    pos, heights = 0, []
    for w in line.get("words", []):
        ws, we = pos, pos + len(w["text"])
        if we > m.start("num") and ws < m.end("num") and re.search(r"\d", w["text"]):
            heights.append(w["bbox"]["height"])
        pos = we + 1
    return float(max(heights)) if heights else None


MRP_RE = re.compile(
    r"(?P<label>m\s*[.,]?\s*r\s*[.,]?\s*p\s*[.,]?|maximum\s+retail\s+price|retail\s+price)"
    r"\s*(?:\((?:incl[^)]*)\))?\s*[:\-=]?\s*(?:incl\.?\s*of\s*all\s*taxes\s*[:\-]?\s*)?"
    r"(?P<cur>₹|rs\.?|inr|[%zZ=?Xx*€¥&](?=\s*\d))?\s*(?P<num>[0-9OoIlS]{1,6}(?:[.,][0-9Oo]{1,2})?)\s*(?P<tail>/-)?",
    re.I)
TAX_INCL_RE = re.compile(r"incl(?:usive|\.)?\s*(?:of)?\s*all\s*taxes|inclusive\s+of\s+(?:all\s+)?taxes|incl\.?\s*of\s*taxes", re.I)
TAX_EXCL_RE = re.compile(r"(?:plus|\+|excl(?:usive|\.)?\s*of)\s*(?:all\s*)?(?:local\s*)?taxes|taxes\s*extra", re.I)


def _extract_mrp(lines, i, ctx):
    line = lines[i]
    text = line["text"]
    match = _ocr_match_text(text)
    m = MRP_RE.search(match)
    src, t = line, text
    if not m and re.search(r"\bm\s*\.?\s*r\s*\.?\s*p\b|maximum\s+retail\s+price", match, re.I):
        nxt = lines_below(lines, i, 1)
        if nxt:
            m2 = re.search(r"(?P<cur>₹|rs\.?|inr)?\s*(?P<num>\d[\d,]*(?:\.\d{1,2})?)", nxt[0]["text"], re.I)
            if m2:
                m, src, t = m2, nxt[0], nxt[0]["text"]
    if not m:
        return None
    amount, repaired = parse_amount(m.group("num"))
    if amount is None:
        return None
    around = " ".join(l["text"] for l in [line] + lines_below(lines, i, 2))
    conf = _words_conf(src, m.start("num"), m.end("num"))
    if repaired:
        conf -= 8
    cur_raw = (m.group("cur") or "").strip() if "cur" in m.groupdict() else ""
    alts = _rupee_glyph_alternatives(m.group("num"), cur_raw)
    currency_note = "" if cur_raw.lower().startswith(("₹", "rs", "inr")) or not cur_raw else \
        f"Rupee symbol read by OCR as '{cur_raw}'"
    bbox = _words_bbox(src, m.start(), m.end()) if src is line else _union([line["bbox"], src["bbox"]])
    return Candidate("mrp", f"₹{amount:,.2f}",
                     {"amount": amount, "currency": "INR", "raw": m.group(0).strip(),
                      "inclusive_of_taxes": bool(TAX_INCL_RE.search(around)),
                      "tax_exclusive_wording": bool(TAX_EXCL_RE.search(around)), "ocr_repaired": repaired,
                      "amount_alternatives": alts},
                     conf, ctx["image_id"], ctx["image_name"], ctx["side"],
                     text if src is line else f"{text} / {src['text']}", bbox, True, currency_note)


DATE_LABEL_RE = re.compile(
    r"(?P<label>(?:month\s*(?:&|and)\s*year\s*of\s*(?:mfg|manufacture|packing|pkg|import))|date\s*of\s*(?:mfg|manufacture|packing|pkg|import)"
    r"|mfg\.?\s*(?:date|dt\.?|on)?|mfd\.?\s*(?:date|on)?|manufactured\s*(?:date|dt\.?|on)?|packed\s*(?:on|date|dt\.?)?|pkd\.?\s*(?:on|date|dt\.?)?(?!\s*by)|pkg\.?\s*(?:date|dt\.?)|packing\s*date|imported\s*on)",
    re.I)
EXPIRY_LABEL_RE = re.compile(
    r"(?P<label>best\s*before|use\s*(?:by|before|within)|exp(?:iry)?\.?\s*(?:date|dt\.?)?|expires?\s*(?:on)?|\bb[b8]\s*:)", re.I)
# finer-grained labels for the structured output
MFG_ONLY_RE = re.compile(
    r"(?P<label>(?:month\s*(?:&|and)\s*year\s*of\s*(?:mfg|manufacture))|date\s*of\s*(?:mfg|manufacture)"
    r"|mfg\.?\s*(?:date|dt\.?|on)?|mfd\.?\s*(?:date|on)?|manufactured\s*(?:date|dt\.?|on)?|manufacturing\s*date)", re.I)
PKD_ONLY_RE = re.compile(
    r"(?P<label>(?:month\s*(?:&|and)\s*year\s*of\s*(?:packing|pkg))|date\s*of\s*(?:packing|pkg)"
    r"|packed\s*(?:on|date|dt\.?)?|pkd\.?\s*(?:on|date|dt\.?)?(?!\s*by)|pkg\.?\s*(?:date|dt\.?)|packing\s*date)", re.I)
BB_ONLY_RE = re.compile(r"(?P<label>best\s*before|\bb[b8]\s*:)", re.I)
EXP_ONLY_RE = re.compile(r"(?P<label>\buse\s*(?:by|before|within)|\bexp(?:iry)?\b\.?\s*(?:date|dt\.?)?|\bexpires?\s*(?:on)?)", re.I)
DURATION_FIELDS = {"best_before", "best_before_label", "expiry_date"}
DURATION_RE = re.compile(r"(?P<n>\d{1,3})\s*(?P<u>months?|days?|years?|yrs?)\s*(?:from|after)?\s*(?P<ref>(?:the\s*)?(?:date\s*of\s*)?(?:mfg|manufacture|packing|packaging|pkd|mfd)?)", re.I)


def _extract_date(field_name, label_re, lines, i, ctx):
    line = lines[i]
    match = _ocr_match_text(line["text"])
    m = label_re.search(match)
    if not m:
        return None
    if field_name in ("mfg_date", "manufacture_date", "packed_on") and re.search(r"\bby\b", match[m.end():m.end() + 6], re.I):
        return None
    if field_name == "expiry_date" and BB_ONLY_RE.search(match[:m.start()]):
        return None                      # "Best Before Use Within 12 months" is a best-before declaration
    after = match[m.end():]
    date = parse_date(after)
    src, used_next = line, False
    if not date and field_name in DURATION_FIELDS:
        dur = DURATION_RE.search(after)
        if dur:
            conf = _words_conf(line, m.start(), len(line["text"]))
            return Candidate(field_name, dur.group(0).strip(),
                             {"type": "duration", "amount": int(dur.group("n")), "unit": dur.group("u").lower(),
                              "reference": dur.group("ref").strip() or None},
                             conf, ctx["image_id"], ctx["image_name"], ctx["side"], line["text"], line["bbox"])
    if not date:
        nxt = lines_below(lines, i, 1)
        if nxt:
            date = parse_date(nxt[0]["text"])
            if date:
                src, used_next = nxt[0], True
            elif field_name in DURATION_FIELDS:
                dur = DURATION_RE.search(nxt[0]["text"])
                if dur:
                    return Candidate(field_name, dur.group(0).strip(),
                                     {"type": "duration", "amount": int(dur.group("n")), "unit": dur.group("u").lower(),
                                      "reference": dur.group("ref").strip() or None},
                                     float(np.mean([line["confidence"], nxt[0]["confidence"]])), ctx["image_id"],
                                     ctx["image_name"], ctx["side"], f"{line['text']} / {nxt[0]['text']}",
                                     _union([line["bbox"], nxt[0]["bbox"]]))
    if not date:
        # label printed but date is on a separate stamp/batch area the OCR could not associate
        return Candidate(field_name, "", {"label_only": True, "label": m.group("label")}, line["confidence"] - 25,
                         ctx["image_id"], ctx["image_name"], ctx["side"], line["text"], line["bbox"], False,
                         "Declaration label found but the date value was not readable (often ink-jet printed)")
    value = f"{date['month']:02d}/{date['year']}" if not date["day"] else f"{date['day']:02d}/{date['month']:02d}/{date['year']}"
    conf = src["confidence"] if used_next else _words_conf(line, m.start(), len(line["text"]))
    return Candidate(field_name, value, {"type": "date", **date, "label": m.group("label").strip()}, conf,
                     ctx["image_id"], ctx["image_name"], ctx["side"],
                     line["text"] + (f" / {src['text']}" if used_next else ""),
                     _union([line["bbox"], src["bbox"]]) if used_next else line["bbox"])


CARE_RE = re.compile(r"consumer\s*care|customer\s*care|consumer\s*complaints?|customer\s*complaints?|customer\s*service|"
                     r"for\s*(?:any\s*)?(?:consumer\s*|customer\s*)?(?:complaints?|queries|feedback|grievances?)|"
                     r"contact\s*us|toll[\s-]*free|helpline|care\s*(?:no|number|cell)|write\s*to\s*us|"
                     r"e-?mail\s*(?:us|id)?\s*:|\bcontact\s*:", re.I)


def _extract_consumer_care(lines, i, ctx):
    line = lines[i]
    if not CARE_RE.search(_ocr_match_text(line["text"])):
        return None
    used = [line]
    for nxt in lines_below(lines, i, 5):
        if FIELD_KEYWORDS.search(_ocr_match_text(nxt["text"])) and not CARE_RE.search(_ocr_match_text(nxt["text"])):
            break
        used.append(nxt)
    text = " ".join(u["text"] for u in used)
    phones = [p.strip() for p in PHONE_RE.findall(text) if len(re.sub(r"\D", "", p)) >= 10]
    emails = [e.replace(" ", "") for e in EMAIL_RE.findall(text)]
    # trim continuation to the lines actually carrying details
    last = 0
    for k, u in enumerate(used):
        if PHONE_RE.search(u["text"]) or EMAIL_RE.search(u["text"]) or k == 0:
            last = k
    used = used[:max(1, last + 1)]
    complete = bool(phones or emails)
    return Candidate("consumer_care", "; ".join(filter(None, [", ".join(phones), ", ".join(emails)])) or line["text"],
                     {"phones": phones, "emails": emails, "has_address": bool(PIN_RE.search(text))},
                     float(np.mean([u["confidence"] for u in used])), ctx["image_id"], ctx["image_name"], ctx["side"],
                     " / ".join(u["text"] for u in used), _union([u["bbox"] for u in used]), complete,
                     "" if complete else "Consumer-care heading found but no telephone number or e-mail was readable")


ORIGIN_RE = re.compile(r"(?P<label>country\s*of\s*origin|made\s*in|product\s*of|manufactured\s*in|origin)\s*[:\-]?\s*(?P<rest>.*)", re.I)


def _extract_origin(lines, i, ctx):
    line = lines[i]
    m = ORIGIN_RE.search(_ocr_match_text(line["text"]))
    if not m:
        return None
    rest = m.group("rest")
    country = find_country(rest)
    src = line
    if not country:
        nxt = lines_below(lines, i, 1)
        if nxt and find_country(nxt[0]["text"]):
            country, src = find_country(nxt[0]["text"]), nxt[0]
    if not country:
        return None
    return Candidate("country_of_origin", country, {"country": country, "label": m.group("label")},
                     src["confidence"], ctx["image_id"], ctx["image_name"], ctx["side"],
                     line["text"] if src is line else f"{line['text']} / {src['text']}",
                     line["bbox"] if src is line else _union([line["bbox"], src["bbox"]]))


USP_RE = re.compile(
    r"(?P<label>unit\s*sale\s*price|unit\s*price|u\s*\.?\s*s\s*\.?\s*p\b\.?|price\s*per)\s*[:\-=]?\s*(?:₹|rs\.?|inr|[%zZ=?])?\s*"
    r"(?P<num>[0-9OoIl]+(?:[.,][0-9Oo]{1,3})?)\s*(?:/-)?\s*(?:per|/)\s*(?P<per>\d+(?:\.\d+)?)?\s*(?P<unit>[a-zA-Z]+)",
    re.I)


def _extract_usp(lines, i, ctx):
    line = lines[i]
    match = _ocr_match_text(line["text"])
    m = USP_RE.search(line["text"]) or USP_RE.search(match)
    if m and m.string is match:
        line = {**line, "text": match}
    if not m and re.search(r"(?:unit\s*sale\s*price|\bu\s*\.?\s*s\s*\.?\s*p\b\.?)\s*[:\-=]?\s*$", match, re.I):
        # label on one line, amount on the next ("Unit Sale Price:" / "₹57.00 per 100 g")
        nxt = lines_below(lines, i, 1)
        if nxt:
            n = nxt[0]
            joined = {**n, "text": line["text"].rstrip() + " " + n["text"],
                      "words": list(line.get("words", [])) + list(n.get("words", [])),
                      "confidence": float(np.mean([line["confidence"], n["confidence"]])),
                      "bbox": _union([line["bbox"], n["bbox"]])}
            jm = _ocr_match_text(joined["text"])
            m = USP_RE.search(joined["text"]) or USP_RE.search(jm)
            if m:
                line = {**joined, "text": m.string}
    if not m:
        if re.search(r"unit\s*sale\s*price|\bu\s*\.?\s*s\s*\.?\s*p\b", match, re.I):
            return Candidate("unit_sale_price", line["text"], {"unparsed": True}, line["confidence"] - 20,
                             ctx["image_id"], ctx["image_name"], ctx["side"], line["text"], line["bbox"], False,
                             "Unit sale price label found but amount/unit not parsable")
        return None
    amount, repaired = parse_amount(m.group("num"))
    unit = lookup_unit(m.group("unit"))
    if amount is None or unit is None:
        return None
    per = float(m.group("per")) if m.group("per") else 1.0
    cur_m = re.search(r"(₹|rs\.?|inr|[%zZ=?¥*&])\s*[0-9OoIl]", line["text"][m.end("label"):m.end("num")], re.I)
    alts = _rupee_glyph_alternatives(m.group("num"), cur_m.group(1) if cur_m else "")
    return Candidate("unit_sale_price", f"₹{amount:,.2f} per {m.group('per') or ''}{' ' if m.group('per') else ''}{m.group('unit')}",
                     {"amount": amount, "per_quantity": per, "unit_symbol": unit["symbol"], "dimension": unit["dimension"],
                      "per_base": per * unit["factor"], "ocr_repaired": repaired, "amount_alternatives": alts},
                     _words_conf(line, m.start(), m.end()) - (8 if repaired else 0), ctx["image_id"], ctx["image_name"],
                     ctx["side"], line["text"], _words_bbox(line, m.start(), m.end()))


SIMPLE_PATTERNS = {
    "fssai_license": re.compile(r"(?:fssai|lic(?:ense|ence)?\.?\s*no)\.?\s*(?:lic(?:ense|ence)?\.?)?\s*(?:no\.?)?\s*[:\-]?\s*(?P<v>[0-9OoIl](?:\s?[0-9OoIl]){13})(?!\d)", re.I),
    "batch_number": re.compile(r"(?:\bbatch|\blot|\bb\.\s*no|\bb\s*no\b|\bb\.\s*n\b)\s*(?:no|number|code|#)?\.?\s*[:\-]?\s*(?P<v>(?=[A-Z0-9/\-]*\d)[A-Z0-9][A-Z0-9/\-]{2,15})", re.I),
    "registration_number": re.compile(r"(?:l\.?\s*m\.?\s*)?(?:regn|registration|reg)\.?\s*(?:no|number)\.?\s*[:\-]?\s*(?P<v>[A-Z0-9][A-Z0-9/\-]{3,30})", re.I),
    "bis_mark": re.compile(r"(?P<v>\bR-\d{8}\b|\bIS\s*\d{3,5}(?::\s*\d{4})?|\bCM/L-?\d{7,10})", re.I),
    "size_dimensions": re.compile(r"\b(?:size|dimensions?)\s*[:\-]\s*(?P<v>[\w .x×*/-]{0,20}\d[\w .x×*/-]{0,20})", re.I),
}
PRESENCE_PATTERNS = {
    "ingredients": re.compile(r"\bingredients?\b|\bcomposition\b", re.I),
    "nutrition_info": re.compile(r"nutrition(?:al)?\s*(?:information|facts|value)|energy\s*\(?k\s*cal", re.I),
}


def _extract_simple(field_name, lines, i, ctx):
    line = lines[i]
    match = _ocr_match_text(line["text"])
    if field_name in PRESENCE_PATTERNS:
        m = PRESENCE_PATTERNS[field_name].search(match)
        if not m:
            return None
        return Candidate(field_name, line["text"][:120], {"present": True}, line["confidence"], ctx["image_id"],
                         ctx["image_name"], ctx["side"], line["text"], line["bbox"])
    m = None
    if field_name == "batch_number":
        # batch codes are matched on the raw text: the matching view rewrites "RS1125A" as a rupee amount
        raw = line["text"]
        m = SIMPLE_PATTERNS[field_name].search(raw)
        if m:
            match = raw
    m = m or SIMPLE_PATTERNS[field_name].search(match)
    if not m:
        return None
    v = m.group("v").strip()
    if field_name == "fssai_license":
        v, _ = (re.sub(r"[Oo]", "0", re.sub(r"[Il]", "1", v.replace(" ", ""))), True)
    return Candidate(field_name, v, {"value": v}, _words_conf(line, m.start(), m.end()), ctx["image_id"],
                     ctx["image_name"], ctx["side"], line["text"], _words_bbox(line, m.start(), m.end()))


GENERIC_LABEL_RE = re.compile(r"(?P<label>generic\s*name|common\s*name|product\s*name|name\s*of\s*(?:the\s*)?(?:commodity|product)|description)\s*[:\-]\s*(?P<v>.+)", re.I)


def _extract_generic(lines, i, ctx):
    line = lines[i]
    m = GENERIC_LABEL_RE.search(_ocr_match_text(line["text"]))
    if m and len(m.group("v").strip()) >= 3:
        return Candidate("generic_name", m.group("v").strip(), {"method": "label"},
                         _words_conf(line, m.start("v"), m.end("v")), ctx["image_id"], ctx["image_name"], ctx["side"],
                         line["text"], line["bbox"])
    hint = ctx.get("product_hint_tokens")
    if hint:
        tokens = set(re.findall(r"[a-z]{3,}", line["text"].lower()))
        from .line_roles import plausible_name
        t = line["text"].strip()
        if (tokens and len(hint & tokens) / len(hint) >= 0.6 and len(hint & tokens) / len(tokens) >= 0.5
                and len(t) <= 60 and t[:1].isalnum() and not t[:1].islower() and "(" not in t and ")" not in t
                and plausible_name(t)):
            return Candidate("generic_name", line["text"].strip(), {"method": "matched_product_name"},
                             line["confidence"] - 5, ctx["image_id"], ctx["image_name"], ctx["side"],
                             line["text"], line["bbox"], True, "Matched against the product name entered by the inspector")
    return None


EXTRACTORS = [
    ("manufacturer_packer", lambda L, i, c: _extract_party("manufacturer_packer", L, i, c)),
    ("importer", lambda L, i, c: _extract_party("importer", L, i, c)),
    ("generic_name", _extract_generic),
    ("net_quantity", _extract_net_quantity),
    ("mrp", _extract_mrp),
    ("mfg_date", lambda L, i, c: _extract_date("mfg_date", DATE_LABEL_RE, L, i, c)),
    ("best_before", lambda L, i, c: _extract_date("best_before", EXPIRY_LABEL_RE, L, i, c)),
    ("consumer_care", _extract_consumer_care),
    ("country_of_origin", _extract_origin),
    ("unit_sale_price", _extract_usp),
    ("manufacture_date", lambda L, i, c: _extract_date("manufacture_date", MFG_ONLY_RE, L, i, c)),
    ("packed_on", lambda L, i, c: _extract_date("packed_on", PKD_ONLY_RE, L, i, c)),
    ("expiry_date", lambda L, i, c: _extract_date("expiry_date", EXP_ONLY_RE, L, i, c)),
    ("best_before_label", lambda L, i, c: _extract_date("best_before_label", BB_ONLY_RE, L, i, c)),
] + [(f, (lambda name: lambda L, i, c: _extract_simple(name, L, i, c))(f))
     for f in ("fssai_license", "batch_number", "registration_number", "bis_mark", "size_dimensions",
               "ingredients", "nutrition_info")]


# ------------------------------------------------------------------ aggregation
def _iou(a, b):
    ax1, ay1, bx1, by1 = a["x"] + a["width"], a["y"] + a["height"], b["x"] + b["width"], b["y"] + b["height"]
    iw = max(0, min(ax1, bx1) - max(a["x"], b["x"])); ih = max(0, min(ay1, by1) - max(a["y"], b["y"]))
    inter = iw * ih
    smaller = min(a["width"] * a["height"], b["width"] * b["height"]) or 1
    return inter / smaller


def _rank(c: Candidate) -> float:
    r = c.confidence + (15 if c.complete else 0) + (5 if c.side == "front" else 0) + min(len(c.value), 40) * 0.1
    if c.field in ("brand_name", "product_name") and c.side == "front":
        r += 15         # brand / product name belong to the principal display panel
    if c.field == "manufacturer_packer" and c.normalized.get("role") != "marketer":
        r += 8          # the manufacturer / packer declaration is preferred over a "marketed by" line
    if c.field in ("mrp", "net_quantity") and c.side == "front":
        r += 10         # principal display panel declaration wins over a repeat elsewhere (both are kept)
    return r


def _status_for(c: Candidate) -> str:
    if not c.complete:
        return NEEDS_VERIFICATION
    if c.confidence >= 70:
        return DETECTED
    if c.confidence >= 45:
        return LOW_CONFIDENCE
    return NEEDS_VERIFICATION


def _cluster(cands: list[Candidate]) -> list[list[Candidate]]:
    clusters: list[list[Candidate]] = []
    for c in sorted(cands, key=_rank, reverse=True):
        for cl in clusters:
            if cl[0].image_id == c.image_id and _iou(cl[0].bbox, c.bbox) > 0.3:
                cl.append(c)
                break
        else:
            clusters.append([c])
    return clusters


def _value_key(c: Candidate):
    if c.field == "mrp":
        return round(c.normalized.get("amount", 0), 2)
    if c.field == "net_quantity":
        return round(c.normalized.get("base_value", 0) or 0, 3)
    return re.sub(r"\W", "", c.value.lower())[:30]


_LABEL_ONLY = re.compile(r"^[\W_]*(?:[A-Za-z.&/]+\s*){1,5}[:.\-]?\s*$")


def _join_label_value_rows(lines: list[dict]) -> list[dict]:
    """Table-style labels print the declaration name and its value in separate cells of the same row
    ("MRP" | "Rs. 124.50"). For every label-only line add a joined line "label value" (the originals are kept),
    so the normal extractors see the pair."""
    extra = []
    for i, l in enumerate(lines):
        t = l["text"].strip()
        if len(t) > 32 or not _LABEL_ONLY.match(t) or not FIELD_KEYWORDS.search(_ocr_match_text(t)) and \
                not re.search(r"\b(?:lic|lot|b\.?\s*no|usp|price|packed|pkd|mfg|exp)\b", t, re.I):
            continue
        a = l["bbox"]
        best = None
        for j, r in enumerate(lines):
            if j == i:
                continue
            b = r["bbox"]
            vov = min(a["y"] + a["height"], b["y"] + b["height"]) - max(a["y"], b["y"])
            gap = b["x"] - (a["x"] + a["width"])
            if vov >= 0.5 * min(a["height"], b["height"]) and gap > -0.2 * a["height"] and gap < 25 * a["height"]:
                if best is None or gap < best[0]:
                    best = (gap, j)
        if best is None:
            continue
        r = lines[best[1]]
        extra.append({**l, "text": f"{t} {r['text'].strip()}", "confidence": min(l["confidence"], r["confidence"]),
                      "bbox": _union([l["bbox"], r["bbox"]]), "words": l.get("words", []) + r.get("words", []),
                      "joined_row": True})
    return lines + extra if extra else lines


def _grow_name(lines: list[dict], i: int, ok) -> list[int]:
    """A brand / product name printed over two or three lines: add adjacent lines of the same type size."""
    from .line_roles import KEYWORDS
    chosen = [i]
    base = lines[i]["bbox"]
    h = max(1, base["height"])
    for direction in (1, -1):
        cur = base
        for _ in range(2):
            best = None
            for j, l in enumerate(lines):
                if j in chosen or not ok(j):
                    continue
                b = l["bbox"]
                gap = (b["y"] - (cur["y"] + cur["height"])) if direction == 1 else (cur["y"] - (b["y"] + b["height"]))
                overlap = min(cur["x"] + cur["width"], b["x"] + b["width"]) - max(cur["x"], b["x"])
                if -0.3 * h <= gap <= 0.9 * h and overlap > 0 and 0.8 <= b["height"] / h <= 1.25 \
                        and not KEYWORDS.search(l["text"]) and sum(c.isdigit() for c in l["text"]) == 0 \
                        and len(re.sub(r"[^A-Za-z]", "", l["text"])) >= 2:
                    if best is None or gap < best[0]:
                        best = (gap, j)
            if best is None:
                break
            chosen.append(best[1])
            cur = lines[best[1]]["bbox"]
    return sorted(chosen, key=lambda j: lines[j]["bbox"]["y"])


def _role_candidates(img: dict, mode: str) -> list[Candidate]:
    """Brand / product-name candidates for one image from the trained line-role model (or the layout heuristic)."""
    from . import line_roles
    lines = [l for l in img.get("merged", []) if l.get("text", "").strip()]
    if not lines or mode == "off":
        return []
    model = line_roles.load_model() if mode in ("auto", "model") else None
    out = []
    def make(role, idxs, method, conf, note, extra):
        ls = [lines[j] for j in idxs]
        text = " ".join(l["text"].strip() for l in ls)
        return Candidate(role, text, {"method": method, "lines": len(ls), **extra}, conf, img["image_id"],
                         img["image_name"], img["side"], " / ".join(l["text"] for l in ls), _union([l["bbox"] for l in ls]),
                         True, note)
    if model is not None:
        assigned = model.assign(lines)
        P = model.predict_proba(lines) if assigned else None
        taken = {i for i, _ in assigned.values()}
        for role, (i, p) in assigned.items():
            j_role = model.roles.index(role)
            idxs = _grow_name(lines, i, lambda j: j not in taken and P[j, j_role] >= 0.25)
            conf = 0.5 * float(np.mean([lines[j]["confidence"] for j in idxs])) + 50 * p
            out.append(make(role, idxs, "line_role_model", conf, f"Identified by the line-role model (p={p:.2f}) - verify",
                            {"probability": round(p, 3)}))
        # a layout the model has not seen (e.g. product name printed smaller than the net quantity): fall back
        # to the layout heuristic for any role the model left empty
        missing = [r for r in ("brand_name", "product_name") if r not in assigned]
        if missing and mode == "auto":
            cand = [i for i in line_roles.heuristic_candidates(lines) if i not in taken]
            for role in missing:
                other = assigned.get("product_name" if role == "brand_name" else "brand_name")
                if other is not None:     # brand is printed above the product name
                    oy = lines[other[0]]["bbox"]["y"]
                    cand_r = [i for i in cand if (lines[i]["bbox"]["y"] > oy) == (role == "product_name")]
                else:
                    cand_r = cand
                if cand_r:
                    i = cand_r[0]
                    cand.remove(i)
                    out.append(make(role, [i], "layout_heuristic", float(lines[i]["confidence"]) - 20,
                                    "Largest remaining text on the panel (layout heuristic) - verify", {}))
    elif mode in ("auto", "heuristic"):
        roles = line_roles.heuristic_roles(lines)
        taken = set(roles.values())
        for role, i in roles.items():
            idxs = _grow_name(lines, i, lambda j: j not in taken) if role == "product_name" else [i]
            conf = float(np.mean([lines[j]["confidence"] for j in idxs])) - 20
            out.append(make(role, idxs, "layout_heuristic", conf, "Largest text on the panel (layout heuristic) - verify", {}))
    return out


def extract_fields(images_ocr: list[dict], product_name: str = "", roles: str = "auto") -> dict[str, FieldResult]:
    """
    images_ocr: [{image_id, image_name, side, passes:[{lines:[...]}], merged:[...]}]
    roles: how brand / product name are found - auto (trained model if present, else heuristic) | model |
           heuristic | off
    """
    hint = set(re.findall(r"[a-z]{3,}", (product_name or "").lower())) or None
    cands: dict[str, list[Candidate]] = {f: [] for f in FIELD_LABELS}
    for img in images_ocr:
        ctx = {"image_id": img["image_id"], "image_name": img["image_name"], "side": img["side"],
               "product_hint_tokens": hint}
        line_sets = [p["lines"] for p in img.get("passes", []) if p.get("lines")] or [img.get("merged", [])]
        line_sets = [_join_label_value_rows(ls) for ls in line_sets]
        for lines in line_sets:
            for i in range(len(lines)):
                for fname, fn in EXTRACTORS:
                    try:
                        c = fn(lines, i, ctx)
                    except Exception:  # an extractor must never break the pipeline
                        c = None
                    if c:
                        c.confidence = float(max(0.0, min(99.0, c.confidence)))
                        cands[fname].append(c)
        try:
            for c in _role_candidates(img, roles):
                c.confidence = float(max(0.0, min(99.0, c.confidence)))
                if c.confidence < 40:      # too uncertain to show - report as not detected instead of noise
                    continue
                cands[c.field].append(c)
        except Exception:  # the model must never break extraction
            import logging
            logging.getLogger("safemetric.extraction").exception("line-role model failed")

    results: dict[str, FieldResult] = {}
    for fname, label in FIELD_LABELS.items():
        fr = FieldResult(field=fname, label=label)
        cl = _cluster(cands[fname])
        if cl:
            best_per_cluster = [sorted(c, key=_rank, reverse=True)[0] for c in cl]
            best = best_per_cluster[0]
            fr.value, fr.normalized, fr.confidence = best.value, best.normalized, round(best.confidence, 1)
            fr.source_image_id, fr.source_image, fr.source_side = best.image_id, best.image_name, best.side
            fr.evidence, fr.bbox, fr.note = best.evidence, best.bbox, best.note
            fr.status = _status_for(best)
            fr.alternatives = [
                {"value": c.value, "normalized": c.normalized, "confidence": round(c.confidence, 1),
                 "source_image_id": c.image_id, "source_image": c.image_name, "side": c.side,
                 "evidence": c.evidence, "bbox": c.bbox, "same_value": _value_key(c) == _value_key(best)}
                for c in best_per_cluster[1:6] if c.complete
            ]
        results[fname] = fr
    resolve_price_ambiguity(results)
    _generic_from_product_name(results, images_ocr)
    return results


# common / generic commodity names. When the product name printed on the pack contains one of these
# ("HOMOGENISED TONED MILK", "Basmati Rice", "Refined Sunflower Oil") it is the commodity's common name.
COMMODITY_TERMS = re.compile(
    r"\b(?:milk|curd|dahi|yog(?:h)?urt|butter|ghee|cheese|paneer|cream|lassi|buttermilk|chaas|ice\s*cream|"
    r"rice|atta|flour|maida|suji|sooji|rava|besan|wheat|dal|daal|pulses?|lentils?|poha|oats|muesli|cornflakes|"
    r"oil|sugar|jaggery|salt|honey|tea|coffee|biscuits?|cookies?|crackers?|chips|namkeen|bhujia|noodles|pasta|"
    r"vermicelli|sauce|ketchup|jam|pickle|chutney|spices?|masala|powder|chilli|turmeric|haldi|cumin|jeera|"
    r"coriander|pepper|juice|drink|beverage|water|soda|squash|chocolate|candy|toffee|bread|cake|rusk|"
    r"soap|shampoo|conditioner|detergent|cleaner|dishwash|toothpaste|toothbrush|cream|lotion|face\s*wash|"
    r"hand\s*wash|deodorant|talc|hair\s*oil|sanitizer|notebook|pens?|pencils?|eraser|battery|batteries|bulb)\b",
    re.I)


def _generic_from_product_name(results: dict, images_ocr: list[dict]) -> None:
    """If no generic name is labelled, adopt the product name - or else the largest headline-style line - that
    contains a recognised commodity term ("HOMOGENISED TONED MILK"). Reported as found-by-inference: verify."""
    from .line_roles import KEYWORDS, plausible_name
    g, pn = results.get("generic_name"), results.get("product_name")
    if g is None or g.found:
        return
    if pn is not None and pn.found and pn.value and COMMODITY_TERMS.search(pn.value):
        m = COMMODITY_TERMS.search(pn.value)
        for k in ("value", "confidence", "source_image_id", "source_image", "source_side", "evidence", "bbox", "status"):
            setattr(g, k, getattr(pn, k))
    else:
        best = None
        for img in images_ocr:
            lines = [l for l in img.get("merged", []) if l.get("text", "").strip()]
            if not lines:
                continue
            med = float(np.median([l["bbox"]["height"] for l in lines]))
            for l in lines:
                t = l["text"].strip()
                if (len(t.split()) <= 6 and ":" not in t and plausible_name(t) and not KEYWORDS.search(t)
                        and l["bbox"]["height"] >= 0.6 * med and COMMODITY_TERMS.search(t)):
                    key = (img.get("side") == "front", l["bbox"]["height"])
                    if best is None or key > best[0]:
                        best = (key, img, l)
        if best is None:
            return
        _, img, l = best
        m = COMMODITY_TERMS.search(l["text"])
        g.value, g.confidence = l["text"].strip(), round(float(l.get("confidence", 80)) - 10, 1)
        g.source_image_id, g.source_image, g.source_side = img["image_id"], img["image_name"], img["side"]
        g.evidence, g.bbox = l["text"], l["bbox"]
        g.status = "DETECTED" if g.confidence >= 60 else "LOW_CONFIDENCE"
    g.normalized = {"method": "commodity_term", "term": m.group(0).lower()}
    g.note = f"Contains the commodity term '{m.group(0)}' - verify it is the common name"


def _rupee_glyph_alternatives(num: str, cur_raw: str) -> list[float]:
    """
    Tesseract's English model has no '₹' glyph; when the symbol touches the digits it is often
    read as a leading 7, 2 or 3 ('₹185' -> '7185'). If no currency symbol was read, keep the
    reading without that leading digit as an ALTERNATIVE. It is only adopted later if another
    declaration on the same package corroborates it (see resolve_price_ambiguity).
    """
    if cur_raw:
        return []
    int_part = re.split(r"[.,]", num)[0]
    if len(int_part) >= 2 and int_part[0] in "723":
        alt, _ = parse_amount(num[1:])
        return [alt] if alt else []
    return []


def resolve_price_ambiguity(results: dict) -> None:
    """Pick MRP / USP readings that are mutually consistent with the declared net quantity."""
    mrp, usp, qty = results.get("mrp"), results.get("unit_sale_price"), results.get("net_quantity")
    if not (mrp and usp and qty and mrp.found and usp.found and qty.found):
        return
    q, u = qty.normalized, usp.normalized
    if not q.get("base_value") or not u.get("per_base") or q.get("dimension") != u.get("dimension"):
        return
    m_read = [mrp.normalized.get("amount")] + list(mrp.normalized.get("amount_alternatives") or [])
    u_read = [u.get("amount")] + list(u.get("amount_alternatives") or [])
    if len(m_read) + len(u_read) == 2:
        return
    best = None
    for i, rm in enumerate(m_read):
        for j, ru in enumerate(u_read):
            if not rm or not ru:
                continue
            expected = rm / (q["base_value"] / u["per_base"])
            err = abs(expected - ru) / max(expected, 0.01)
            if best is None or err < best[0]:
                best = (err, i, j, rm, ru)
    if not best or best[0] > 0.02 or (best[1] == 0 and best[2] == 0):
        return
    _, i, j, rm, ru = best
    note = "Leading digit interpreted as the ₹ symbol (OCR glyph confusion) - corroborated by MRP / quantity / unit sale price consistency"
    if i:
        mrp.normalized = {**mrp.normalized, "amount": rm, "ocr_reading": m_read[0], "currency_glyph_resolved": True}
        mrp.value = f"₹{rm:,.2f}"
        mrp.note = note
    if j:
        usp.normalized = {**u, "amount": ru, "ocr_reading": u_read[0], "currency_glyph_resolved": True}
        usp.value = re.sub(r"₹[\d,]+(?:\.\d+)?", f"₹{ru:,.2f}", usp.value, count=1)
        usp.note = note


def normalized_text(text: str) -> str:
    return "\n".join(canonical(t) for t in text.splitlines())


def qualifying_expressions() -> list[str]:
    return units_table().get("qualifying_expressions", [])
