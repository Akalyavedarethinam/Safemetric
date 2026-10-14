"""
Structured field-extraction evaluation (precision / recall / F1 / exact match).

Two modes:
  text  - datasets/field_extraction/<split>.jsonl : ground-truth label text with synthetic OCR noise
          (clean / light / medium / heavy) -> extractor -> structured output. Measures the extractor alone.
  ocr   - end-to-end: saved OCR predictions of real rendered images (evaluation/results/predictions/
          ocr_<tag>_<split>.jsonl, produced by evaluate_ocr.py) -> extractor. Measures OCR + extraction.

    python evaluation/evaluate_extraction.py --mode text --split test
    python evaluation/evaluate_extraction.py --mode ocr --ocr-tag hybrid_auto --split test
    python evaluation/evaluate_extraction.py --mode ocr --ocr-tag hybrid_auto --roles heuristic   # no ML model
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "evaluation"))

from metrics import FIELDS, Scorer  # noqa: E402

SIZE_PX = {"xxl": 62, "xl": 48, "l": 36, "m": 28, "s": 22, "xs": 19}


def jl(p):
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            yield json.loads(line)


def pseudo_lines(lines: list[dict]) -> list[dict]:
    """Give text-only lines a plausible layout (size class -> height, top-to-bottom order)."""
    out, y = [], 40
    for l in lines:
        h = SIZE_PX.get(l.get("size", "s"), 22)
        x, words = 50, []
        for w in l["text"].split(" "):
            if not w:
                continue
            ww = max(6, int(len(w) * h * 0.55))
            words.append({"text": w, "confidence": 92.0, "bbox": {"x": x, "y": y, "width": ww, "height": h}})
            x += ww + int(h * 0.3)
        if not words:
            continue
        out.append({"text": " ".join(w["text"] for w in words), "confidence": 92.0,
                    "bbox": {"x": 50, "y": y, "width": max(10, x - 50), "height": h}, "words": words})
        y += int(h * 1.45)
    return out


def run_text(split: str, roles: str, limit: int, level: str = ""):
    from app import config
    from app.services import extraction, structured
    from app.services.textclean import clean_text
    sc, by_level = Scorer(), defaultdict(Scorer)
    rows = list(jl(ROOT / "datasets" / "field_extraction" / f"{split}.jsonl"))
    if level:
        rows = [r for r in rows if r["noise_level"] == level]
    if limit:
        rows = rows[:limit]
    for ex in rows:
        if config.OCR_TEXT_CLEAN:        # the same post-OCR clean-up the OCR stage applies
            ex["lines"] = [{**l, "text": clean_text(l["text"])} for l in ex["lines"]]
        imgs = []
        for k, side in enumerate(("front", "back")):
            ls = pseudo_lines([l for l in ex["lines"] if l["panel"] == side])
            if ls:
                imgs.append({"image_id": k + 1, "image_name": f"{side}.txt", "side": side, "passes": [{"lines": ls}],
                             "merged": ls})
        pred = structured.structured_output(extraction.extract_fields(imgs, "", roles=roles))
        sc.add(ex["expected"], pred, example_id=ex["id"])
        by_level[ex["noise_level"]].add(ex["expected"], pred, example_id=ex["id"])
    return sc, {k: v for k, v in sorted(by_level.items())}


def run_ocr(split: str, tag: str, roles: str, limit: int):
    from app.services import extraction, structured
    anns = {a["image"]: a for a in jl(ROOT / "datasets" / "ocr_annotations" / f"{split}.jsonl")}
    sc, by_cond = Scorer(), defaultdict(Scorer)
    rows = list(jl(ROOT / "evaluation" / "results" / "predictions" / f"ocr_{tag}_{split}.jsonl"))
    if limit:
        rows = rows[:limit]
    for r in rows:
        a = anns[r["image"]]
        imgs = [{"image_id": 1, "image_name": Path(r["image"]).name, "side": "front",
                 "passes": [{"lines": p["lines"]} for p in r["passes"]], "merged": r["lines"]}]
        pred = structured.structured_output(extraction.extract_fields(imgs, "", roles=roles))
        ignore = set(a.get("fields_not_fully_visible", []))
        sc.add(a["expected_fields"], pred, ignore, example_id=r["image"])
        for c in a["conditions"]:
            by_cond[c].add(a["expected_fields"], pred, ignore, example_id=r["image"])
    return sc, {k: v for k, v in sorted(by_cond.items())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["text", "ocr"], default="text")
    ap.add_argument("--split", default="test")
    ap.add_argument("--ocr-tag", default="hybrid_auto")
    ap.add_argument("--roles", default="auto", choices=["auto", "model", "heuristic", "off"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--level", default="", help="text mode: only this noise level")
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    if a.mode == "text":
        sc, groups = run_text(a.split, a.roles, a.limit, a.level)
        name = a.tag or f"extraction_text_{a.roles}_{a.split}"
    else:
        sc, groups = run_ocr(a.split, a.ocr_tag, a.roles, a.limit)
        name = a.tag or f"extraction_ocr_{a.ocr_tag}_{a.roles}_{a.split}"
    s = sc.summary()
    out = {"mode": a.mode, "split": a.split, "roles": a.roles, "ocr_tag": a.ocr_tag if a.mode == "ocr" else None,
           "overall": s, "groups": {k: {kk: vv for kk, vv in v.summary().items() if kk != "per_field"}
                                    for k, v in groups.items()},
           "errors": {f: sc.errors[f][:15] for f in FIELDS}}
    p = ROOT / "evaluation" / "results" / f"{name}.json"
    p.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{name}: micro P/R/F1 = {s['micro_precision']:.3f}/{s['micro_recall']:.3f}/{s['micro_f1']:.3f}  "
          f"macro F1 = {s['macro_f1']:.3f}  doc exact = {s['document_exact_match']:.3f}  (n={s['documents']})")
    for f, v in s["per_field"].items():
        print(f"  {f:22s} P={v['precision']:.3f} R={v['recall']:.3f} F1={v['f1']:.3f} acc={v['accuracy']:.3f} n={v['support']}")
    for k, v in out["groups"].items():
        print(f"  [{k}] micro F1={v['micro_f1']:.3f} exact={v['document_exact_match']:.3f} n={v['documents']}")


if __name__ == "__main__":
    main()
