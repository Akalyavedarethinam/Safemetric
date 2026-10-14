"""
Line-role classification: which OCR line is the BRAND, which is the PRODUCT NAME, which is a tagline ...

Rules find declarations that carry a label ("MRP", "Net Wt", "Batch No") very reliably, but a brand or product
name has no label - it is recognised by *how* it is printed (largest type, near the top of the front panel,
no digits, not a legal phrase). That is what the small trained model in this module learns.

  * features(lines)       - per-line layout + text features (shared by training and inference)
  * heuristic_roles(...)  - rule-only baseline: largest line = brand, next largest = product
  * LineRoleModel         - scikit-learn pipeline (char n-gram TF-IDF + layout features -> logistic regression)
                            trained by training/train_line_roles.py, stored in models/extraction/.
The model only proposes brand / product-name candidates; it never decides compliance.
"""
from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path

import numpy as np

log = logging.getLogger("safemetric.line_roles")

ROLES = ["brand_name", "product_name", "net_quantity", "mrp", "unit_sale_price", "date", "batch_number",
         "manufacturer", "address", "importer", "customer_care", "fssai_license", "country_of_origin",
         "ingredients", "nutrition_info", "other"]
FIELD_TO_ROLE = {
    "brand_name": "brand_name", "product_name": "product_name", "net_quantity": "net_quantity", "mrp": "mrp",
    "mrp_conflict": "mrp", "unit_sale_price": "unit_sale_price", "mfg_date": "date", "packed_on": "date",
    "expiry_date": "date", "best_before": "date", "batch_number": "batch_number",
    "manufacturer_name": "manufacturer", "marketed_by": "manufacturer", "manufacturer_address": "address",
    "importer_address": "address", "importer": "importer", "customer_care": "customer_care",
    "fssai_license": "fssai_license", "country_of_origin": "country_of_origin", "ingredients": "ingredients",
    "nutrition_info": "nutrition_info",
}
KEYWORDS = re.compile(
    r"\b(m\.?\s*r\.?\s*p|mrp|net|wt|weight|qty|quantity|vol|contents?|best|before|use|exp|expiry|mfg|mfd|pkd|packed|"
    r"batch|lot|b\.?\s*no|fssai|lic|licen[cs]e|customer|consumer|care|email|e-mail|ph|phone|toll|manufactured|"
    r"marketed|imported|importer|origin|made|ingredients|nutrition|energy|protein|store|keep|price|usp|incl|"
    r"taxes|synthetic|sample)\b", re.I)
# regulatory marks, logos and panel headings that are printed large but are never a brand / product name
NOT_A_NAME = re.compile(
    r"^\W*(?:fssai|agmark|isi|bis|halal|veg(?:etarian)?|non[\s-]*veg(?:etarian)?|front\s*view|back\s*view|side\s*view|"
    r"top\s*view|nutrition(?:al)?\s*(?:information|facts|info)|ingredients?|lic(?:en[cs]e)?\.?\s*no\.?|"
    r"recycle|recyclable|tetra\s*pak|best\s*before|use\s*by|manufactured\s*by|marketed\s*by|"
    r"(?:[a-z]+\s+){0,2}flavou?r(?:ed)?|new|improved|new\s*&?\s*improved|with\s+vitamins.*|limited\s+edition)\W*$", re.I)
COMPANY = re.compile(r"\b(?:pvt|ltd|limited|llp|inc|gmbh|co-operative|industries|private)\b\.?", re.I)
UNIT = re.compile(r"\d\s*(?:kg|g|gm|gms|ml|l|ltr|litre|n|pcs|pieces|sheets|pairs|m)\b", re.I)
DATE = re.compile(r"\b\d{1,2}[./-]\d{2,4}\b|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*\d{2}", re.I)
NUMERIC_FEATURES = ["rel_h", "h_over_max", "h_rank", "y_rel", "x_rel", "w_rel", "top_rank", "n_chars", "n_words",
                    "upper", "digit", "punct", "colon", "keyword", "unit", "date", "email", "pin", "conf",
                    "is_largest", "is_second"]


def _geom(line: dict) -> tuple[float, float, float, float]:
    b = line["bbox"]
    return float(b["x"]), float(b["y"]), float(b["width"]), float(b["height"])


def features(lines: list[dict]) -> tuple[list[str], np.ndarray]:
    """lines: OCR lines of ONE image (text, bbox, confidence) -> (texts, numeric feature matrix)."""
    if not lines:
        return [], np.zeros((0, len(NUMERIC_FEATURES)))
    g = np.array([_geom(l) for l in lines])
    hs = g[:, 3]
    med = float(np.median(hs)) or 1.0
    mx = float(hs.max()) or 1.0
    x0, y0 = g[:, 0].min(), g[:, 1].min()
    x1, y1 = (g[:, 0] + g[:, 2]).max(), (g[:, 1] + g[:, 3]).max()
    W, H = max(1.0, x1 - x0), max(1.0, y1 - y0)
    order_h = np.argsort(-hs, kind="stable")
    h_rank = np.empty(len(lines))
    h_rank[order_h] = np.arange(len(lines))
    order_y = np.argsort(g[:, 1], kind="stable")
    y_rank = np.empty(len(lines))
    y_rank[order_y] = np.arange(len(lines))
    n = max(1, len(lines) - 1)
    rows, texts = [], []
    for i, l in enumerate(lines):
        t = l["text"]
        letters = [c for c in t if c.isalpha()]
        rows.append([
            hs[i] / med, hs[i] / mx, h_rank[i] / n, (g[i, 1] + hs[i] / 2 - y0) / H, (g[i, 0] - x0) / W, g[i, 2] / W,
            y_rank[i] / n, min(len(t), 120) / 120, min(len(t.split()), 20) / 20,
            sum(c.isupper() for c in letters) / max(1, len(letters)), sum(c.isdigit() for c in t) / max(1, len(t)),
            sum(not c.isalnum() and not c.isspace() for c in t) / max(1, len(t)), float(":" in t),
            float(bool(KEYWORDS.search(t))), float(bool(UNIT.search(t))), float(bool(DATE.search(t))),
            float("@" in t), float(bool(re.search(r"\b\d{6}\b", t))), float(l.get("confidence", 90)) / 100,
            float(h_rank[i] == 0), float(h_rank[i] == 1),
        ])
        texts.append(t)
    return texts, np.array(rows, dtype=np.float64)


def plausible_name(text: str) -> bool:
    """A brand / product name is not a company name, an address, an e-mail or mostly digits."""
    words = re.findall(r"[A-Za-z]{4,}", text)
    if any(not re.search(r"[aeiouyAEIOUY]", w) for w in words):   # OCR garbage such as "vgmpH"
        return False
    if re.match(r"^[a-z].*\.$", text.strip()):                     # the end of a sentence ("from packing.")
        return False
    if re.match(r"^\W*[a-z]{1,3}\)", text):                        # a clipped fragment such as "ons) of ..."
        return False
    return not (NOT_A_NAME.search(text) or COMPANY.search(text) or "@" in text or text.count(",") >= 1 or
                sum(c.isdigit() for c in text) > 3 or len(re.sub(r"[^A-Za-z]", "", text)) < 2)


def heuristic_candidates(lines: list[dict]) -> list[int]:
    """Lines that could be a brand / product name, largest type first."""
    # a brand / product name is printed larger than the body text of the panel
    med = float(np.percentile([l["bbox"]["height"] for l in lines], 25)) if len(lines) >= 5 else 0.0
    cand = [i for i, l in enumerate(lines)
            if len(re.sub(r"[^A-Za-z]", "", l["text"])) >= 3 and not KEYWORDS.search(l["text"])
            and sum(c.isdigit() for c in l["text"]) <= 2 and "," not in l["text"] and "@" not in l["text"]
            and not COMPANY.search(l["text"]) and plausible_name(l["text"]) and l["bbox"]["height"] >= 1.2 * med]
    cand.sort(key=lambda i: -lines[i]["bbox"]["height"])
    return cand


def heuristic_roles(lines: list[dict]) -> dict[str, int]:
    """Rule-only baseline: brand = largest text line without digits / declaration keywords,
    product = next largest such line below it. Returns {'brand_name': idx, 'product_name': idx}."""
    cand = heuristic_candidates(lines)
    out = {}
    if cand:
        out["brand_name"] = cand[0]
        by = lines[cand[0]]["bbox"]["y"]
        below = [i for i in cand[1:] if lines[i]["bbox"]["y"] > by]
        if below:
            out["product_name"] = below[0]
    return out


class LineRoleModel:
    def __init__(self, bundle: dict):
        self.pipeline = bundle["pipeline"]
        self.roles = list(bundle["roles"])
        self.meta = bundle.get("meta", {})
        self.thresholds = bundle.get("thresholds", {"brand_name": 0.35, "product_name": 0.35})

    def predict_proba(self, lines: list[dict]) -> np.ndarray:
        texts, num = features(lines)
        if not texts:
            return np.zeros((0, len(self.roles)))
        import pandas as pd
        X = pd.DataFrame(num, columns=NUMERIC_FEATURES)
        X["text"] = texts
        return self.pipeline.predict_proba(X)

    def assign(self, lines: list[dict]) -> dict[str, tuple[int, float]]:
        """Pick at most one line per role (brand, product): the most probable line above the role threshold that
        is not obviously something else (a company name, an address, an e-mail or a number)."""
        if not lines:
            return {}
        P = self.predict_proba(lines)
        out = {}
        taken = set()
        for role in ("brand_name", "product_name"):
            j = self.roles.index(role)
            for i in np.argsort(-P[:, j]):
                if P[i, j] < self.thresholds.get(role, 0.35):
                    break
                if i in taken or not plausible_name(lines[i]["text"]):
                    continue
                out[role] = (int(i), float(P[i, j]))
                taken.add(int(i))
                break
        return out


# ------------------------------------------------------------------------------ portable model
# The trained scikit-learn pipeline is exported to plain numpy arrays (vocabulary, idf, scaler, weights), so
# the application needs neither scikit-learn nor pandas and is immune to pickle / version mismatches.

def _char_wb_ngrams(text: str, lo: int, hi: int) -> list[str]:
    """Exact re-implementation of scikit-learn's analyzer='char_wb' (lowercase=True)."""
    doc = " ".join(text.lower().split())
    grams = []
    for w in doc.split():
        w = " " + w + " "
        L = len(w)
        for n in range(lo, hi + 1):
            offset = 0
            grams.append(w[offset:offset + n])
            while offset + n < L:
                offset += 1
                grams.append(w[offset:offset + n])
            if offset == 0:
                break
    return grams


def export_portable(pipeline, roles, thresholds: dict, meta: dict, path: Path) -> None:
    pre = pipeline.named_steps["features"]
    tfidf = pre.named_transformers_["text"]
    scaler = pre.named_transformers_["layout"]
    clf = pipeline.named_steps["clf"]
    vocab = tfidf.vocabulary_
    terms = [None] * len(vocab)
    for t, i in vocab.items():
        terms[i] = t
    np.savez_compressed(path, idf=tfidf.idf_.astype(np.float64), mean=scaler.mean_.astype(np.float64),
                        scale=scaler.scale_.astype(np.float64), coef=clf.coef_.astype(np.float64),
                        intercept=clf.intercept_.astype(np.float64))
    info = {"terms": terms, "roles": list(roles), "thresholds": thresholds, "meta": meta,
            "ngram_range": list(tfidf.ngram_range), "sublinear_tf": bool(tfidf.sublinear_tf),
            "numeric_features": NUMERIC_FEATURES}
    path.with_suffix(".json").write_text(__import__("json").dumps(info), encoding="utf-8")


class PortableLineRoleModel(LineRoleModel):
    def __init__(self, npz_path: Path):
        import json
        arr = np.load(npz_path)
        info = json.loads(npz_path.with_suffix(".json").read_text(encoding="utf-8"))
        self.idf, self.mean, self.scale = arr["idf"], arr["mean"], arr["scale"]
        self.coef, self.intercept = arr["coef"], arr["intercept"]
        self.index = {t: i for i, t in enumerate(info["terms"])}
        self.lo, self.hi = info["ngram_range"]
        self.sublinear = info["sublinear_tf"]
        self.roles = info["roles"]
        self.thresholds = info["thresholds"]
        self.meta = info["meta"]
        self.n_text = len(self.idf)

    def predict_proba(self, lines: list[dict]) -> np.ndarray:
        texts, num = features(lines)
        if not texts:
            return np.zeros((0, len(self.roles)))
        W_text, W_num = self.coef[:, :self.n_text], self.coef[:, self.n_text:]
        out = np.zeros((len(texts), len(self.roles)))
        scaled = (num - self.mean) / np.where(self.scale == 0, 1.0, self.scale)
        for r, t in enumerate(texts):
            counts: dict[int, int] = {}
            for g in _char_wb_ngrams(t, self.lo, self.hi):
                j = self.index.get(g)
                if j is not None:
                    counts[j] = counts.get(j, 0) + 1
            if counts:
                idx = np.fromiter(counts.keys(), dtype=np.int64)
                tf = np.fromiter(counts.values(), dtype=np.float64)
                if self.sublinear:
                    tf = 1.0 + np.log(tf)
                v = tf * self.idf[idx]
                v /= np.linalg.norm(v) or 1.0
                z = W_text[:, idx] @ v
            else:
                z = np.zeros(len(self.roles))
            out[r] = z + W_num @ scaled[r] + self.intercept
        out -= out.max(axis=1, keepdims=True)
        e = np.exp(out)
        return e / e.sum(axis=1, keepdims=True)


@lru_cache(maxsize=4)
def load_model(path: str | None = None) -> LineRoleModel | None:
    """Load the portable model (.npz + .json); a scikit-learn .joblib is accepted as a fallback."""
    from .. import config
    p = Path(path or config.LINE_ROLE_MODEL)
    npz = p.with_suffix(".npz")
    try:
        if npz.exists() and npz.with_suffix(".json").exists():
            return PortableLineRoleModel(npz)
        if p.suffix == ".joblib" and p.exists():
            import joblib
            return LineRoleModel(joblib.load(p))
    except Exception as exc:
        log.warning("line-role model %s could not be loaded: %s", p, exc)
    return None
