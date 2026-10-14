"""
OCR text normalisation.

Two different things happen here and they are deliberately kept apart:

1. canonical(text)  - a *matching* form used only to find declaration keywords
   (M.R.P -> MRP, Rs./INR/₹ -> ₹, Net Wt -> NET WEIGHT ...). The original OCR text is
   always kept as evidence.

2. repair_number(token) - fixes O/0, I/1, S/5, B/8 confusions ONLY when the token is
   already mostly numeric (context makes the reading unambiguous). Any repair is
   reported so the extractor can lower its confidence. Nothing is replaced blindly.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent.parent / "rules" / "config"


@lru_cache
def units_table() -> dict:
    return json.loads((CONFIG_DIR / "units.json").read_text(encoding="utf-8"))


_CANON_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bM\s*[.,]?\s*R\s*[.,]?\s*P\s*[.,]?", re.I), "MRP "),
    (re.compile(r"\bmaximum\s+retail\s+price\b", re.I), "MRP "),
    (re.compile(r"\b(?:Rs|RS|rs)\s*[.,/]?\s*(?=\d)"), "₹"),
    (re.compile(r"\bRs\b\.?", re.I), "₹"),
    (re.compile(r"\bINR\b\.?\s*", re.I), "₹"),
    (re.compile(r"\bnet\s*(?:qty|quantity|qnty|quan)\b\.?", re.I), "NET QUANTITY"),
    (re.compile(r"\bnet\s*(?:wt|weight|wght)\b\.?", re.I), "NET WEIGHT"),
    (re.compile(r"\bnet\s*(?:vol|volume)\b\.?", re.I), "NET VOLUME"),
    (re.compile(r"\bpkd\b\.?", re.I), "PACKED"),
    (re.compile(r"\bmfd\b\.?|\bmfg\b\.?|\bmanufd\b\.?", re.I), "MANUFACTURED"),
    (re.compile(r"\bcustomer\s+care\b|\bconsumer\s+complaints?\b|\bcustomer\s+service\b", re.I), "CONSUMER CARE"),
    (re.compile(r"\bmade\s+in\b|\bproduct\s+of\b", re.I), "COUNTRY OF ORIGIN"),
    (re.compile(r"\bu\s*\.\s*s\s*\.\s*p\b\.?", re.I), "UNIT SALE PRICE"),
    (re.compile(r"\s*([:;])\s*"), r"\1 "),
    (re.compile(r"\s{2,}"), " "),
]


def canonical(text: str) -> str:
    t = text.replace("|", "I") if re.search(r"[A-Za-z]\|[A-Za-z]", text) else text
    for pat, rep in _CANON_RULES:
        t = pat.sub(rep, t)
    return t.strip().upper()


_DIGITISH = {"O": "0", "o": "0", "D": "0", "Q": "0", "I": "1", "l": "1", "|": "1", "i": "1",
             "S": "5", "s": "5", "B": "8", "Z": "2", "z": "2", "G": "6"}


def repair_number(token: str) -> tuple[str, bool]:
    """Repair a numeric token such as '1O0' or '5OO.5O' -> ('100', True). Returns (value, repaired)."""
    core = token.strip()
    digits = sum(ch.isdigit() for ch in core)
    letters = [ch for ch in core if ch in _DIGITISH]
    other = [ch for ch in core if not (ch.isdigit() or ch in _DIGITISH or ch in ".,")]
    if not core or other or digits == 0 or (digits < len(letters) and not core[0].isdigit()):
        return core, False
    fixed = "".join(_DIGITISH.get(ch, ch) for ch in core)
    return fixed, fixed != core


def parse_amount(token: str) -> tuple[float | None, bool]:
    """'1,250.00' -> 1250.0.  Also accepts OCR-repairable tokens."""
    fixed, repaired = repair_number(token)
    fixed = fixed.replace(",", "")
    if fixed.count(".") > 1:
        head, _, tail = fixed.rpartition(".")
        fixed = head.replace(".", "") + "." + tail
    try:
        return float(fixed), repaired
    except ValueError:
        return None, repaired


def lookup_unit(raw: str) -> dict | None:
    key = raw.strip().strip(".").lower().replace("²", "2")
    key = {"mi": "ml", "m1": "ml", "kq": "kg"}.get(key, key)     # OCR confusions of unit symbols (mI, kq)
    if key in ("ltr.", "gm."):
        key = key.rstrip(".")
    info = units_table()["units"].get(key)
    if info is None:
        return None
    return {**info, "raw": raw.strip()}


# a regex alternation of every known unit, longest first so 'kg' wins over 'g'
def unit_pattern() -> str:
    keys = sorted(units_table()["units"].keys(), key=len, reverse=True)
    return "|".join(re.escape(k) for k in keys)


_MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], start=1)}
_MONTHS.update({"SEPT": 9, "JUNE": 6, "JULY": 7})

DATE_RE = re.compile(
    r"(?P<d1>\b[0-3O]?[0-9O])[\s./-](?P<m1>[01O]?[0-9O])[\s./-](?P<y1>(?:19|20)?[0-9O]{2})\b"      # 12/08/2026
    r"|(?P<m2>\b[01O]?[0-9O])\s*[./-]\s*(?P<y2>(?:19|20)[0-9O]{2}|[0-9O]{2})\b"                  # 08/2026, 08-26
    r"|(?:(?P<d3>\b[0-3]?\d)\s*[\s./-]?\s*)?(?P<m3>JAN|FEB|MAR|APR|MAY|JUNE?|JULY?|AUG|SEPT?|OCT|NOV|DEC)[A-Z]*\.?\s*[\s./,'-]?\s*(?P<y3>(?:19|20)\d{2}|\d{2})\b",
    re.I,
)


def parse_date(text: str) -> dict | None:
    """Find the first month/year style date in text. Returns {'month','year','day','raw'}."""
    for m in DATE_RE.finditer(text):
        g = m.groupdict()
        try:
            if g["m1"]:
                day, month, year = int(repair_number(g["d1"])[0]), int(repair_number(g["m1"])[0]), repair_number(g["y1"])[0]
            elif g["m2"]:
                day, month, year = None, int(repair_number(g["m2"])[0]), repair_number(g["y2"])[0]
            else:
                day = int(g["d3"]) if g["d3"] else None
                month = _MONTHS[g["m3"].upper()[:4] if g["m3"].upper()[:4] in _MONTHS else g["m3"].upper()[:3]]
                year = g["y3"]
            year = int(year)
            if year < 100:
                year += 2000
        except (ValueError, KeyError, TypeError):
            continue
        if not (1 <= month <= 12) or not (1990 <= year <= 2100) or (day is not None and not 1 <= day <= 31):
            continue
        return {"day": day, "month": month, "year": year, "raw": m.group(0).strip()}
    return None


PHONE_RE = re.compile(r"(?<![\d])(?:(?:\+?91[\s-]?)?(?:1800|1860)[\s-]?\d{3}[\s-]?\d{3,4}"
                      r"|(?:\+?91[\s-]?)?\(?0?\d{2,4}\)?[\s-]?\d{3,4}[\s-]?\d{4}"
                      r"|(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5})(?![\d])")
EMAIL_RE = re.compile(r"[\w.+-]+\s?@\s?[\w-]+(?:\.[\w-]+)+")
PIN_RE = re.compile(r"(?<!\d)[1-9]\d{2}\s?\d{3}(?!\d)")

COUNTRIES = {
    "INDIA", "CHINA", "USA", "UNITED STATES", "U.S.A", "UK", "UNITED KINGDOM", "GERMANY", "FRANCE", "ITALY",
    "SPAIN", "JAPAN", "KOREA", "SOUTH KOREA", "TAIWAN", "THAILAND", "VIETNAM", "MALAYSIA", "SINGAPORE",
    "INDONESIA", "SRI LANKA", "BANGLADESH", "NEPAL", "UAE", "UNITED ARAB EMIRATES", "SAUDI ARABIA",
    "TURKEY", "SWITZERLAND", "NETHERLANDS", "BELGIUM", "AUSTRALIA", "NEW ZEALAND", "CANADA", "BRAZIL",
    "MEXICO", "SOUTH AFRICA", "EGYPT", "ISRAEL", "PHILIPPINES", "POLAND", "GREECE", "PORTUGAL",
    "IRELAND", "DENMARK", "SWEDEN", "NORWAY", "FINLAND", "AUSTRIA", "HONG KONG", "RUSSIA", "UKRAINE",
    "ARGENTINA", "CHILE", "PERU", "KENYA",
}


def find_country(text: str) -> str | None:
    up = re.sub(r"[^A-Z. ]", " ", text.upper())
    for c in sorted(COUNTRIES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(c)}\b", up):
            return c.title() if len(c) > 3 else c
    return None
