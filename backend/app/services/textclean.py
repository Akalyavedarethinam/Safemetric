"""
Post-OCR text clean-up (applied to every OCR line; the raw reading is always kept as `raw_text`).

Only *context-safe* corrections are made - things that are unambiguous on a package label:

1. digit repair inside numeric tokens     6O0001 -> 600001,  O8/2026 -> 08/2026,  199.0O -> 199.00
                                          26O8 inside SM26O8A -> SM2608A (O between two digits)
2. I / l confusion in ALL-CAPS words      MAGGl -> MAGGI
3. spaces the recogniser dropped          BatchNo:SM2608A -> Batch No: SM2608A,  perkg -> per kg,
                                          12months -> 12 months, ConsumerCare -> Consumer Care
4. whitespace normalisation               collapse runs of spaces, trim

Anything else (words, names, addresses) is left exactly as read.
"""
from __future__ import annotations

import re

_NUMERIC_TOKEN = re.compile(r"^[\dOoIl|S.,/:\-]+$")
_DIGIT_MAP = {"O": "0", "o": "0", "I": "1", "l": "1", "|": "1", "S": "5"}

# label words that recognisers commonly glue together -> spaced form
_GLUED = [
    (r"(?i)\b(batch|lot)(no|number|code)\b", r"\1 \2"),
    (r"(?i)\b(b)\.?(no)\b\.?", r"\1.No."),
    (r"(?i)\b(consumer|customer)(care|service|complaints?)\b", r"\1 \2"),
    (r"(?i)\b(net)(wt|weight|qty|quantity|vol|volume|content|contents)\b", r"\1 \2"),
    (r"(?i)\b(best)(before)\b", r"\1 \2"),
    (r"(?i)\b(use)(by|before)\b", r"\1 \2"),
    (r"(?i)\b(unit)(sale)(price)\b", r"\1 \2 \3"),
    (r"(?i)\b(unit)(saleprice|price)\b", r"\1 \2"),
    (r"(?i)\b(sale)(price)\b", r"\1 \2"),
    (r"(?i)\b(country)(of)(origin)\b", r"\1 \2 \3"),
    (r"(?i)\b(countryof)(origin)\b", r"\1 \2"),
    (r"(?i)\b(manufactured|packed|marketed|imported|mfd\.?|pkd\.?|mktd\.?)(by|on)\b", r"\1 \2"),
    (r"(?i)\b(date)(of)(manufacture|packing|mfg|pkg)\b", r"\1 \2 \3"),
    (r"(?i)\b(month)(&|and)(year)\b", r"\1 \2 \3"),
    (r"(?i)\b(year)(of)(packing|manufacture|mfg)\b", r"\1 \2 \3"),
    (r"(?i)\b(inclusive|incl\.?)(of)(all)(taxes)\b", r"\1 \2 \3 \4"),
    (r"(?i)\b(of)(all)(taxes)\b", r"\1 \2 \3"),
    (r"(?i)\b(lic\.?)(no\.?)", r"\1 \2"),
    (r"(?i)\b(fssai)(lic|license|licence|no)", r"\1 \2"),
    (r"(?i)(?<=\bno\.)(?=[A-Z0-9])", " "),
    (r"(?i)(?<=\d)(per)(kg|g|l|ml|litre|gm|unit|piece|n)\b", r" \1 \2"),
    (r"(?i)\b(per)(kg|g|l|ml|litre|gm|unit|piece)\b", r"\1 \2"),
    (r"(?i)(?<=\d)(months?|days?|years?|yrs?)\b", r" \1"),
    (r"(?i)\b(months?|days?|years?)(from|after)\b", r"\1 \2"),
    (r"(?i)\b(from)(packing|manufacture|mfg|date|pkd)\b", r"\1 \2"),
    (r"(?i)\b(made)(in)\b", r"\1 \2"),
    (r"(?i)\b(product)(of)\b", r"\1 \2"),
    (r"(?i)\b(pvt)\.?(ltd)\b", r"Pvt. Ltd"),
    (r"(?i)\b(toll)(free)\b", r"\1 \2"),
]
_GLUED += [
    (r"(?<=[A-Za-z]{2})\.(?=\d)", ". "),                        # "DT.28/01/25" -> "DT. 28/01/25"
    (r"(?i)(?<=\bm\.r\.p\.)(?=[A-Za-z₹0-9])", " "),           # "M.R.P.Rs.65" -> "M.R.P. Rs.65"
    (r"(?i)(?<=\bmrp)(?=(?:rs|₹|inr))", " "),                    # "MRPRs.65" -> "MRP Rs.65"
    (r"(?<=[A-Za-z])-(?=\d{6}\b)", " - "),                        # "Nadu-641085" -> "Nadu - 641085"
    (r"(?<=[a-z]),(?=[A-Z][a-z])", ", "),                          # "Chennai,Tamil" -> "Chennai, Tamil"
]
_GLUED = [(re.compile(p), r) for p, r in _GLUED]
_CAMEL = re.compile(r"(?<=[a-z]{2})(?=[A-Z][a-z]{2})")      # ConsumerCare -> Consumer Care (not iPhone / McCain)
_COLON_GLUE = re.compile(r"(?<=[A-Za-z.)]):(?=[A-Za-z0-9₹])")  # "No:SM26" -> "No: SM26" (not 12:30)


def _repair_numeric_token(tok: str) -> str:
    m = re.match(r"^(Rs\.?|RS\.?|INR|₹)(?=[\dOo])", tok)
    if m:                                             # "Rs.199.O0" -> "Rs." + repaired "199.00"
        return m.group(1) + _repair_numeric_token(tok[m.end():])
    core = tok.strip("()[]")
    if not core or not _NUMERIC_TOKEN.match(core):
        return tok
    digits = sum(c.isdigit() for c in core)
    letters = sum(c in _DIGIT_MAP for c in core)
    # must contain a digit and be anchored by digits (never a word such as "SOS", "OIL", "I")
    if digits == 0 or len(core) < 2:
        return tok
    if digits < letters and not (core[0].isdigit() or core[-1].isdigit()):
        return tok
    if re.fullmatch(r"\d+(?:[.,]\d+)?[lI]", core):          # "5l" = 5 litres, not 51
        return tok
    if core[0] == "S" and not core[1:2].isdigit():
        return tok
    fixed = "".join(_DIGIT_MAP.get(c, c) for c in core)
    return tok.replace(core, fixed)


def _repair_inner_o(tok: str) -> str:
    # O / o surrounded by digits inside an alphanumeric code: SM26O8A -> SM2608A
    return re.sub(r"(?<=\d)[Oo](?=\d)", "0", re.sub(r"(?<=\d)[Oo]{2}(?=\d)", "00", tok))


def _caps_i(tok: str) -> str:
    letters = [c for c in tok if c.isalpha()]
    if len(letters) >= 3 and "l" in tok and sum(c.isupper() for c in letters) >= len(letters) - tok.count("l") \
            and sum(c.isupper() for c in letters) >= 2:
        return tok.replace("l", "I")
    return tok


_PROTECT = re.compile(r"[\w.+-]+\s?@\s?[\w-]+(?:\.[\w-]+)+|\bwww\.[\w.-]+|\b[\w-]+\.(?:com|in|co\.in|org)\b")


def clean_text(text: str) -> str:
    """Clean one OCR line. E-mail and web addresses are protected from every rule."""
    if not text:
        return text
    keep: list[str] = []

    def _stash(m):
        keep.append(m.group(0).replace(" ", ""))
        return f"\x00{len(keep) - 1}\x00"
    t = _clean(_PROTECT.sub(_stash, text))
    return re.sub(r"\x00(\d+)\x00", lambda m: keep[int(m.group(1))], t)


def _clean(text: str) -> str:
    t = text.replace("　", " ").replace("：", ":").replace("，", ",").replace("（", "(").replace("）", ")")
    t = _COLON_GLUE.sub(": ", t)
    for pat, rep in _GLUED:
        t = pat.sub(rep, t)
    t = _CAMEL.sub(" ", t)
    toks = []
    for tok in t.split(" "):
        tok = _repair_numeric_token(tok)
        tok = _repair_inner_o(tok)
        tok = _caps_i(tok)
        toks.append(tok)
    t = " ".join(toks)
    return re.sub(r"\s{2,}", " ", t).strip()
