"""
Train the line-role classifier (brand / product name / declaration type of each OCR line).

Training data (all TRAIN split, never val/test):
  gt   - ground-truth lines of the rendered train images: text with synthetic OCR noise, geometry from the
         annotated quads (made rotation-invariant), label = the field the line declares
  ocr  - real OCR output of train images (evaluation/results/predictions/ocr_<tag>_train.jsonl), each OCR
         line labelled with the GT line it overlaps most; this teaches the model what OCR text really looks like

Model selection on VAL OCR output (C of the logistic regression, data mix); the final number is reported on
TEST OCR output by evaluation/evaluate_extraction.py. Saves models/extraction/line_role_model.joblib (scikit-learn),
the portable numpy export the application loads (line_role_model.npz + .json) and a JSON card with the training
configuration and validation scores.

    python training/train_line_roles.py --ocr-tag hybrid_auto
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from app.services.line_roles import FIELD_TO_ROLE, NUMERIC_FEATURES, ROLES, features  # noqa: E402
from training.datagen import noise  # noqa: E402


def jl(p):
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            yield json.loads(line)


def role_of(field: str) -> str:
    return FIELD_TO_ROLE.get(field, "other")


# ------------------------------------------------------------------------------ GT-derived lines
def _upright(quad, angle_deg):
    q = np.asarray(quad, np.float64)
    a = math.radians(angle_deg)
    R = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    return q @ R.T


def gt_image_lines(ann: dict, rng: random.Random, level: str) -> tuple[list[dict], list[str]]:
    rot = ann["augmentation"].get("rotation", 0.0)
    lines, labels = [], []
    for l in ann["lines"]:
        if not l["visible"] or not l["text"]:
            continue
        q = _upright(l["quad"], rot)
        x0, y0 = q.min(axis=0)
        x1, y1 = q.max(axis=0)
        h = (np.linalg.norm(q[3] - q[0]) + np.linalg.norm(q[2] - q[1])) / 2
        w = (np.linalg.norm(q[1] - q[0]) + np.linalg.norm(q[2] - q[3])) / 2
        lines.append({"text": l["text"], "confidence": rng.uniform(75, 99), "field": l["field"],
                      "bbox": {"x": float(x0), "y": float((y0 + y1) / 2 - h / 2), "width": float(w), "height": float(h)}})
    out = []
    for l in lines:                      # character-level OCR noise per line; geometry stays exact
        parts, _ = noise.noisy_lines([{**l, "fields": [l["field"]]}], level, rng)
        t = " ".join(p["text"] for p in parts).strip()
        if t:
            out.append({**l, "text": t})
    return out, [role_of(l["field"]) for l in out]


# ------------------------------------------------------------------------------ OCR-derived lines
def ocr_image_lines(pred: dict, ann: dict) -> tuple[list[dict], list[str]]:
    from shapely.geometry import Polygon
    gts = [(Polygon(l["quad"]), l["field"]) for l in ann["lines"] if l["visible"] and l["text"]]
    lines, labels = [], []
    for disp, orig in zip(pred["lines"], pred["lines_orig"]):
        try:
            p = Polygon(orig["quad_orig"])
            if not p.is_valid or p.area <= 0:
                continue
        except Exception:
            continue
        best, lab = 0.0, "other"
        for g, f in gts:
            if not g.is_valid or not g.intersects(p):
                continue
            inter = g.intersection(p).area / p.area
            if inter > best:
                best, lab = inter, f
        if best < 0.3:
            lab = "other"
        lines.append(disp)
        labels.append(role_of(lab))
    return lines, labels


def to_frame(image_lines: list[tuple[list[dict], list[str]]]):
    import pandas as pd
    rows, y, groups = [], [], []
    for gi, (lines, labels) in enumerate(image_lines):
        if not lines:
            continue
        texts, num = features(lines)
        df = pd.DataFrame(num, columns=NUMERIC_FEATURES)
        df["text"] = texts
        rows.append(df)
        y.extend(labels)
        groups.extend([gi] * len(labels))
    return pd.concat(rows, ignore_index=True), np.array(y), np.array(groups)


def build_pipeline(C: float):
    from sklearn.compose import ColumnTransformer
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    pre = ColumnTransformer([
        ("text", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=3, max_features=60000,
                                 lowercase=True, sublinear_tf=True), "text"),
        ("layout", StandardScaler(), NUMERIC_FEATURES),
    ])
    clf = LogisticRegression(C=C, max_iter=3000, class_weight="balanced")
    return Pipeline([("features", pre), ("clf", clf)])


def role_selection_score(model, image_lines) -> dict:
    """Image-level brand / product selection accuracy on OCR lines (what the extractor actually uses)."""
    import pandas as pd
    hits = Counter()
    tot = Counter()
    for lines, labels in image_lines:
        if not lines:
            continue
        texts, num = features(lines)
        X = pd.DataFrame(num, columns=NUMERIC_FEATURES)
        X["text"] = texts
        P = model.predict_proba(X)
        roles = list(model.classes_)
        for role in ("brand_name", "product_name"):
            if role not in labels:
                continue
            tot[role] += 1
            j = roles.index(role)
            i = int(np.argmax(P[:, j]))
            hits[role] += labels[i] == role
    return {r: round(hits[r] / tot[r], 4) for r in tot}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "datasets"))
    ap.add_argument("--ocr-tag", default="hybrid_auto", help="predictions tag of OCR output on train / val images")
    ap.add_argument("--C", default="0.3,1,3", help="comma-separated values tried on validation")
    ap.add_argument("--gt-copies", type=int, default=2, help="noisy copies of every GT train image")
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--no-ocr-train", action="store_true", help="train on ground-truth lines only")
    ap.add_argument("--out", default=str(ROOT / "models" / "extraction"))
    a = ap.parse_args()
    rng = random.Random(a.seed)
    data = Path(a.data)
    t0 = time.time()

    train_anns = list(jl(data / "ocr_annotations/train.jsonl"))
    anns_by_img = {x["image"]: x for s in ("train", "val") for x in jl(data / f"ocr_annotations/{s}.jsonl")}
    gt_sets = []
    for ann in train_anns:
        for k in range(a.gt_copies):
            gt_sets.append(gt_image_lines(ann, rng, ["clean", "light", "medium"][k % 3]))
    pred_dir = ROOT / "evaluation" / "results" / "predictions"
    ocr_train, ocr_val = [], []
    p_train = pred_dir / f"ocr_{a.ocr_tag}_train.jsonl"
    if p_train.exists() and not a.no_ocr_train:
        ocr_train = [ocr_image_lines(p, anns_by_img[p["image"]]) for p in jl(p_train) if not p.get("error")]
    p_val = pred_dir / f"ocr_{a.ocr_tag}_val.jsonl"
    if not p_val.exists():
        sys.exit(f"validation OCR predictions missing: {p_val} (run evaluation/evaluate_ocr.py --split val)")
    ocr_val = [ocr_image_lines(p, anns_by_img[p["image"]]) for p in jl(p_val) if not p.get("error")]
    print(f"train images: gt={len(train_anns)} (x{a.gt_copies} noisy copies)  ocr={len(ocr_train)}  val(ocr)={len(ocr_val)}")

    mixes = {"gt_only": gt_sets}
    if ocr_train:
        mixes["gt+ocr"] = gt_sets + ocr_train * 2
    Xv, yv, _ = to_frame(ocr_val)
    results = []
    best = None
    from sklearn.metrics import f1_score
    for mix_name, sets in mixes.items():
        X, y, _ = to_frame(sets)
        for C in [float(c) for c in a.C.split(",")]:
            t = time.time()
            m = build_pipeline(C).fit(X, y)
            pv = m.predict(Xv)
            f1 = f1_score(yv, pv, average="macro")
            sel = role_selection_score(m, ocr_val)
            score = (sel.get("brand_name", 0) + sel.get("product_name", 0)) / 2
            results.append({"mix": mix_name, "C": C, "train_lines": int(len(y)), "val_macro_f1_lines": round(f1, 4),
                            "val_selection_accuracy": sel, "fit_seconds": round(time.time() - t, 1)})
            print(results[-1], flush=True)
            if best is None or score > best[0]:
                best = (score, mix_name, C, m)
    score, mix_name, C, model = best
    print(f"selected: mix={mix_name} C={C} (val brand/product selection {score:.4f})")

    # probability thresholds: the lowest max-probability that is still right 90 % of the time on val
    import pandas as pd
    thresholds = {}
    for role in ("brand_name", "product_name"):
        j = list(model.classes_).index(role)
        pts = []
        for lines, labels in ocr_val:
            if not lines:
                continue
            texts, num = features(lines)
            X = pd.DataFrame(num, columns=NUMERIC_FEATURES)
            X["text"] = texts
            P = model.predict_proba(X)
            i = int(np.argmax(P[:, j]))
            pts.append((P[i, j], labels[i] == role))
        pts.sort(reverse=True)
        th, ok = 0.5, 0
        for k, (p, c) in enumerate(pts, 1):
            ok += c
            if ok / k >= 0.9:
                th = p
        thresholds[role] = round(float(max(0.2, min(th, 0.6))), 3)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    import joblib
    import sklearn
    bundle = {"pipeline": model, "roles": list(model.classes_), "thresholds": thresholds,
              "meta": {"trained": time.strftime("%Y-%m-%d %H:%M"), "mix": mix_name, "C": C, "ocr_tag": a.ocr_tag,
                       "sklearn": sklearn.__version__, "roles_all": ROLES}}
    joblib.dump(bundle, out / "line_role_model.joblib", compress=3)
    # portable export used by the application (numpy only; verified equal to scikit-learn's probabilities)
    from app.services.line_roles import LineRoleModel, PortableLineRoleModel, export_portable
    export_portable(model, list(model.classes_), thresholds, bundle["meta"], out / "line_role_model.npz")
    chk = [lines for lines, _ in ocr_val[:40] if lines]
    diff = max(float(np.abs(LineRoleModel(bundle).predict_proba(ls) -
                            PortableLineRoleModel(out / "line_role_model.npz").predict_proba(ls)).max()) for ls in chk)
    print(f"portable export: max probability difference vs scikit-learn = {diff:.2e}")
    assert diff < 1e-6, "portable export does not reproduce the scikit-learn model"
    card = {"model": "line-role classifier: char 2-4-gram TF-IDF + 21 layout features -> multinomial logistic regression",
            "purpose": "propose brand / product-name lines (and a declaration type for every OCR line)",
            "training_data": "TRAIN split only (synthetic). GT lines with synthetic OCR noise" +
                             (" + real OCR output of train images" if mix_name == "gt+ocr" else ""),
            "selection": "validation split OCR output: brand/product selection accuracy", "selected": {"mix": mix_name, "C": C},
            "thresholds": thresholds, "grid": results, "seconds": round(time.time() - t0, 1),
            "limitations": "Learned on synthetic labels with fictional brands; real packaging with decorative logos, "
                           "stylised type or several brands on one panel will be harder. The extractor always marks "
                           "model-derived names so an inspector can verify them."}
    (out / "line_role_model_card.json").write_text(json.dumps(card, indent=2), encoding="utf-8")
    print(f"saved {out / 'line_role_model.joblib'} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
