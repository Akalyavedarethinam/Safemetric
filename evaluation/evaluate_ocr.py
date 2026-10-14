"""
OCR evaluation on the synthetic label images (text detection + recognition).

    python evaluation/evaluate_ocr.py --engine hybrid --split test
    python evaluation/evaluate_ocr.py --engine tesseract --geometry legacy --no-clean --tag tesseract_original
    python evaluation/evaluate_ocr.py --engine ppocr --limit 50

The full application OCR stage is run exactly as an inspection runs it
(load -> straighten (display image) -> preprocessing variants -> OCR engine(s) -> merge), and the
predicted line boxes are mapped back to the uploaded image with the display transform so they can be
compared with the ground-truth quads.

Metrics (reported overall and per capture condition):
  detection   precision / recall / F1 of text lines, one-to-one matching at polygon IoU >= 0.5.
              GT lines that are partially cut off or illegible are "don't care" (neither TP nor FN, and
              predictions on them are not false positives) - the ICDAR convention.
  recognition CER / WER per GT line: predicted lines are assigned to the GT line they overlap most
              (>= 50 % of the prediction's area), concatenated left-to-right and compared with the GT text.
              A GT line with no prediction counts as all characters deleted.
  page level  bag-of-words recall / precision (order-free), and numeric recall - how many digit groups of the
              GT (prices, dates, PIN / phone / licence numbers, batch digits) were read exactly, spacing ignored.
Every prediction (raw + cleaned text, boxes, all passes) is saved for debugging and for the end-to-end
extraction evaluation.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from rapidfuzz.distance import Levenshtein  # noqa: E402
from shapely.geometry import Polygon  # noqa: E402

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
NUM_RE = re.compile(r"\d+(?:[.,/:\-]\d+)*")


def jl(p):
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            yield json.loads(line)


def poly(q):
    try:
        p = Polygon(q)
        return p if p.is_valid else p.buffer(0)
    except Exception:
        return None


def bbox_quad(b):
    return [[b["x"], b["y"]], [b["x"] + b["width"], b["y"]], [b["x"] + b["width"], b["y"] + b["height"]],
            [b["x"], b["y"] + b["height"]]]


def to_orig(quad, Minv):
    q = np.asarray(quad, np.float64)
    ones = np.ones((q.shape[0], 1))
    r = (Minv @ np.hstack([q, ones]).T).T
    return (r[:, :2] / r[:, 2:3]).tolist()


def norm_tok(t: str) -> str:
    t = t.strip(".,;:()[]{}'\"|/-").replace("₹", "")
    t = re.sub(r"^(rs\.?|inr)", "", t, flags=re.I)
    return t.lower()


def tokens(text: str) -> list[str]:
    return [x for x in (norm_tok(t) for t in text.split()) if x]


# ------------------------------------------------------------------------------ OCR runner
def run_image(path: Path, engine: str, geometry: str):
    from app.services import ocr, preprocess
    data = path.read_bytes()
    t0 = time.time()
    bgr = preprocess.load_image(data)
    display, info = preprocess.make_display_image(bgr, geometry)
    variants, scale, _ = preprocess.build_variants(display)
    res = ocr.run_ocr(variants, scale, display, engine)
    dt = time.time() - t0
    Minv = np.linalg.inv(np.asarray(info["matrix"], np.float64))
    lines = []
    for l in res["lines"]:
        q = l.get("quad") or bbox_quad(l["bbox"])
        lines.append({"text": l["text"], "raw_text": l.get("raw_text", l["text"]), "confidence": l["confidence"],
                      "engine": l.get("engine", ""), "quad_orig": to_orig(q, Minv)})
    return res, info, lines, dt


# ------------------------------------------------------------------------------ scoring
def score_image(ann: dict, pred_lines: list[dict]) -> dict:
    care, dont = [], []
    for l in ann["lines"]:
        if not l["visible"] or not l["text"]:
            continue
        (care if (l["legible"] and not l["partial"]) else dont).append(l)
    gpolys = [poly(l["quad"]) for l in care]
    dpolys = [poly(l["quad"]) for l in dont]
    ppolys = [poly(p["quad_orig"]) for p in pred_lines]

    # ---- detection: one-to-one greedy matching.
    # DetEval-style criterion (primary): the prediction covers >= 70 % of the GT line and >= 40 % of the
    # prediction lies on it - tolerant of the padding detectors add around text. IoU >= 0.5 is also reported.
    pairs, pairs_iou = [], []
    for i, g in enumerate(gpolys):
        for j, p in enumerate(ppolys):
            if g is None or p is None or not g.intersects(p) or p.area <= 0 or g.area <= 0:
                continue
            inter = g.intersection(p).area
            iou = inter / max(g.union(p).area, 1e-6)
            if inter / g.area >= 0.7 and inter / p.area >= 0.4:
                pairs.append((iou, i, j))
            if iou >= 0.5:
                pairs_iou.append((iou, i, j))

    def greedy(pp):
        pp.sort(reverse=True)
        a_, b_ = set(), set()
        for _, i, j in pp:
            if i not in a_ and j not in b_:
                a_.add(i)
                b_.add(j)
        return a_, b_
    mg, mp = greedy(pairs)
    mg_iou, _ = greedy(pairs_iou)
    ignored = set()
    for j, p in enumerate(ppolys):
        if j in mp or p is None or p.area <= 0:
            continue
        if any(d is not None and d.intersects(p) and d.intersection(p).area / p.area > 0.5 for d in dpolys):
            ignored.add(j)
    n_pred = len(ppolys) - len(ignored)
    det = {"tp": len(mg), "tp_iou50": len(mg_iou), "gt": len(gpolys), "pred": n_pred}

    # ---- recognition: many-to-one assignment by coverage of the prediction
    assign = defaultdict(list)
    for j, p in enumerate(ppolys):
        if p is None or p.area <= 0:
            continue
        best, bi, ok = 0.0, None, False
        for i, g in enumerate(gpolys):
            if g is None or not g.intersects(p):
                continue
            inter = g.intersection(p).area
            if inter > best:
                best, bi = inter, i
                ok = inter / p.area >= 0.3 or inter / max(g.area, 1e-6) >= 0.5
        if bi is not None and ok:
            assign[bi].append(j)
    rec = {"en": [0, 0, 0, 0], "mixed": [0, 0, 0, 0]}     # char_edits, chars, word_edits, words
    per_field = defaultdict(lambda: [0, 0])
    for i, gl in enumerate(care):
        js = sorted(assign.get(i, []), key=lambda j: min(x for x, _ in pred_lines[j]["quad_orig"]))
        pt = " ".join(pred_lines[j]["text"] for j in js)
        gt = gl["text"]
        bucket = "en" if not DEVANAGARI.search(gt) else "mixed"
        ce = Levenshtein.distance(gt, pt)
        we = Levenshtein.distance(gt.split(), pt.split())
        r = rec[bucket]
        r[0] += ce
        r[1] += len(gt)
        r[2] += we
        r[3] += len(gt.split())
        per_field[gl["field"]][0] += ce
        per_field[gl["field"]][1] += len(gt)

    # ---- page level (order-free)
    gt_toks = [t for l in care if not DEVANAGARI.search(l["text"]) for t in tokens(l["text"])]
    pr_toks = [t for p in pred_lines for t in tokens(p["text"])]
    from collections import Counter
    gc, pc = Counter(gt_toks), Counter(pr_toks)
    common = sum((gc & pc).values())
    # numeric values (prices, dates, PIN / phone / licence numbers, batch digits) compared as digit groups,
    # independent of spacing: "M.R.P.Rs.65.00" and "M.R.P. Rs. 65.00" both contain "65.00"
    gnum = Counter(n for l in care if not DEVANAGARI.search(l["text"]) for n in NUM_RE.findall(l["text"]))
    pnum = Counter(n for p in pred_lines for n in NUM_RE.findall(p["text"]))
    num_hit = sum((gnum & pnum).values())
    return {"det": det, "rec": rec, "per_field": dict(per_field),
            "bow": {"common": common, "gt": sum(gc.values()), "pred": sum(pc.values())},
            "num": {"hit": num_hit, "gt": sum(gnum.values())}}


def aggregate(rows: list[dict]) -> dict:
    tp = sum(r["score"]["det"]["tp"] for r in rows)
    gt = sum(r["score"]["det"]["gt"] for r in rows)
    pr = sum(r["score"]["det"]["pred"] for r in rows)
    P = tp / pr if pr else 0.0
    R = tp / gt if gt else 0.0
    ti = sum(r["score"]["det"]["tp_iou50"] for r in rows)
    Pi, Ri = (ti / pr if pr else 0.0), (ti / gt if gt else 0.0)
    out = {"images": len(rows), "det_precision": round(P, 4), "det_recall": round(R, 4),
           "det_f1": round(2 * P * R / (P + R), 4) if P + R else 0.0,
           "det_f1_iou50": round(2 * Pi * Ri / (Pi + Ri), 4) if Pi + Ri else 0.0}
    for b in ("en", "mixed"):
        ce = sum(r["score"]["rec"][b][0] for r in rows)
        cn = sum(r["score"]["rec"][b][1] for r in rows)
        we = sum(r["score"]["rec"][b][2] for r in rows)
        wn = sum(r["score"]["rec"][b][3] for r in rows)
        if cn:
            out[f"cer_{b}"] = round(ce / cn, 4)
            out[f"wer_{b}"] = round(we / max(wn, 1), 4)
            out[f"gt_chars_{b}"] = cn
    bc = sum(r["score"]["bow"]["common"] for r in rows)
    out["bow_recall"] = round(bc / max(1, sum(r["score"]["bow"]["gt"] for r in rows)), 4)
    out["bow_precision"] = round(bc / max(1, sum(r["score"]["bow"]["pred"] for r in rows)), 4)
    out["numeric_token_recall"] = round(sum(r["score"]["num"]["hit"] for r in rows) /
                                        max(1, sum(r["score"]["num"]["gt"] for r in rows)), 4)
    out["seconds_per_image"] = round(float(np.mean([r["seconds"] for r in rows])), 2) if rows else 0.0
    out["failed_images"] = sum(1 for r in rows if r.get("error"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "datasets"))
    ap.add_argument("--split", default="test")
    ap.add_argument("--engine", default="hybrid", choices=["hybrid", "ppocr", "tesseract"])
    ap.add_argument("--geometry", default="auto", choices=["auto", "legacy"])
    ap.add_argument("--no-clean", action="store_true", help="disable post-OCR clean-up (original behaviour)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--condition", default="", help="only images with this capture condition (e.g. blurry)")
    ap.add_argument("--tag", default="")
    ap.add_argument("--out", default=str(ROOT / "evaluation" / "results"))
    a = ap.parse_args()
    if a.no_clean:
        os.environ["OCR_TEXT_CLEAN"] = "false"
    from app import config
    config.OCR_TEXT_CLEAN = not a.no_clean
    tag = a.tag or f"{a.engine}_{a.geometry}{'_noclean' if a.no_clean else ''}"
    data, out = Path(a.data), Path(a.out)
    (out / "predictions").mkdir(parents=True, exist_ok=True)
    anns = list(jl(data / f"ocr_annotations/{a.split}.jsonl"))
    if a.condition:
        anns = [x for x in anns if a.condition in x["conditions"]]
    if a.limit:
        anns = anns[:a.limit]
    rows = []
    pred_f = open(out / "predictions" / f"ocr_{tag}_{a.split}.jsonl", "w", encoding="utf-8")
    t0 = time.time()
    for k, ann in enumerate(anns):
        path = data / ann["image"]
        try:
            res, info, lines, dt = run_image(path, a.engine, a.geometry)
            err = None
        except Exception as exc:
            res, info, lines, dt, err = {"lines": [], "passes": []}, {"steps": []}, [], 0.0, f"{type(exc).__name__}: {exc}"
        sc = score_image(ann, lines)
        rows.append({"image": ann["image"], "conditions": ann["conditions"], "heldout_font": ann["heldout_font"],
                     "seconds": dt, "score": sc, "error": err})
        pred_f.write(json.dumps({
            "image": ann["image"], "record_id": ann["record_id"], "engine": a.engine, "geometry": info.get("method"),
            "steps": info.get("steps", []), "matrix": info.get("matrix"), "seconds": round(dt, 2), "error": err,
            "lines": [{k2: v for k2, v in l.items()} for l in res.get("lines", [])],
            "passes": [{"engine": p.get("engine"), "variant": p.get("variant"), "psm": p.get("psm"), "lines": p["lines"]}
                       for p in res.get("passes", [])],
            "lines_orig": lines,
        }, ensure_ascii=False) + "\n")
        if (k + 1) % 25 == 0:
            s = aggregate(rows)
            print(f"[{tag}] {k + 1}/{len(anns)}  CER={s.get('cer_en')}  det_F1={s['det_f1']}  "
                  f"{s['seconds_per_image']}s/img  elapsed {time.time() - t0:.0f}s", flush=True)
    pred_f.close()
    summary = {"tag": tag, "engine": a.engine, "geometry": a.geometry, "text_clean": not a.no_clean,
               "split": a.split, "overall": aggregate(rows)}
    by = defaultdict(list)
    for r in rows:
        for c in r["conditions"]:
            by[c].append(r)
    summary["by_condition"] = {c: aggregate(v) for c, v in sorted(by.items())}
    fields = defaultdict(lambda: [0, 0])
    for r in rows:
        for f, (e, n) in r["score"]["per_field"].items():
            fields[f][0] += e
            fields[f][1] += n
    summary["cer_by_field"] = {f: round(e / n, 4) for f, (e, n) in sorted(fields.items()) if n}
    (out / f"ocr_{tag}_{a.split}.json").write_text(json.dumps({"summary": summary, "images": rows}, indent=1),
                                                  encoding="utf-8")
    print(json.dumps(summary["overall"], indent=2))


if __name__ == "__main__":
    main()
