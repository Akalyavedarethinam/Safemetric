"""
Validate the generated datasets: counts, integrity, annotation/image agreement, diversity and leakage.

    python scripts/validate_datasets.py               # writes datasets/validation_report.json
    python scripts/validate_datasets.py --pixel-sample 400

Exit code is non-zero if a hard check fails (missing / corrupted image, annotation outside the image,
brand or text leakage between splits, or text that does not match the annotated words).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from training.datagen.render import VISIBLE_THRESHOLD  # noqa: E402

SPLITS = ("train", "val", "test")


def jl(p: Path):
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            yield json.loads(line)


def template_key(rec: dict) -> str:
    """Field-order signature (which declarations appear, on which panel, in which order)."""
    return "|".join(f"{p[0]}:{l['field']}" for p in ("front", "back") for l in rec["panels"][p])


def label_style_key(rec: dict) -> str:
    """Wording signature: the label words used for each declaration (e.g. 'Net Wt.' vs 'NET QTY')."""
    parts = []
    for p in ("front", "back"):
        for l in rec["panels"][p]:
            if l["field"] in ("brand_name", "product_name", "other", "declaration", "ingredients", "nutrition_info",
                              "manufacturer_address", "importer_address"):
                continue
            parts.append(l["text"].split(":")[0][:14].lower())
    return "|".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "datasets"))
    ap.add_argument("--pixel-sample", type=int, default=300, help="images whose word boxes are checked for ink")
    ap.add_argument("--allow-missing-images", action="store_true",
                    help="annotations may reference images that are not present (e.g. a trimmed ZIP)")
    a = ap.parse_args()
    data = Path(a.data)
    report: dict = {"hard_failures": [], "warnings": []}
    fail = report["hard_failures"].append
    warn = report["warnings"].append

    # ------------------------------------------------------------------ records
    brands = defaultdict(set)
    texts = defaultdict(set)
    templates = Counter()
    styles = Counter()
    field_counts = Counter()
    cat_counts = Counter()
    defect_counts = Counter()
    n_rec = Counter()
    for s in SPLITS:
        for r in jl(data / f"synthetic_text/records_{s}.jsonl"):
            n_rec[s] += 1
            if r["split"] != s:
                fail(f"record {r['id']} in {s} file but split={r['split']}")
            if not r.get("synthetic"):
                fail(f"record {r['id']} not flagged synthetic")
            brands[s].add(r["brand"])
            texts[s].add("\n".join(l["text"] for p in ("front", "back") for l in r["panels"][p]))
            templates[template_key(r)] += 1
            styles[label_style_key(r)] += 1
            field_counts.update(r["fields"].keys())
            cat_counts[r["category"]] += 1
            defect_counts.update(d.split(":")[0] if not d.startswith("missing") else d for d in r["defects"])
    report["records"] = dict(n_rec)
    report["categories"] = dict(cat_counts)
    report["field_presence"] = dict(field_counts)
    report["defects"] = dict(defect_counts)
    total = sum(n_rec.values())
    report["distinct_texts"] = sum(len(v) for v in texts.values())
    if report["distinct_texts"] < total:
        warn(f"{total - report['distinct_texts']} duplicate record texts")
    report["templates"] = {"distinct": len(templates), "records": total,
                           "most_common_share": round(templates.most_common(1)[0][1] / total, 4),
                           "top5": [c for _, c in templates.most_common(5)]}
    report["label_wording"] = {"distinct": len(styles), "most_common_share": round(styles.most_common(1)[0][1] / total, 4)}
    if templates.most_common(1)[0][1] / total > 0.02:
        warn("one field-order template covers more than 2% of records")

    # leakage
    for x, y in (("train", "val"), ("train", "test"), ("val", "test")):
        b = brands[x] & brands[y]
        t = texts[x] & texts[y]
        report[f"leak_brands_{x}_{y}"] = len(b)
        report[f"leak_texts_{x}_{y}"] = len(t)
        if b:
            fail(f"{len(b)} brands shared by {x} and {y}")
        if t:
            fail(f"{len(t)} identical label texts shared by {x} and {y}")
    fx_inputs = defaultdict(set)
    for s in SPLITS:
        for r in jl(data / f"field_extraction/{s}.jsonl"):
            fx_inputs[s].add(r["input_text"])
            if not r["expected"]:
                warn(f"field example {r['id']} has no expected fields")
    for x, y in (("train", "test"), ("val", "test"), ("train", "val")):
        n = len(fx_inputs[x] & fx_inputs[y])
        report[f"leak_field_inputs_{x}_{y}"] = n
        if n:
            fail(f"{n} identical field-extraction inputs shared by {x} and {y}")
    report["field_examples"] = {s: len(v) for s, v in fx_inputs.items()}

    # ------------------------------------------------------------------ images + annotations
    img_counts, cond_counts, layout_counts = Counter(), Counter(), Counter()
    ann_lines = ann_words = oob = text_mismatch = 0
    missing = sha_bad = size_bad = 0
    rec_ids_by_split = {s: {r["id"] for r in jl(data / f"synthetic_text/records_{s}.jsonl")} for s in SPLITS}
    all_anns = []
    for s in SPLITS:
        p = data / f"ocr_annotations/{s}.jsonl"
        if not p.exists():
            continue
        for r in jl(p):
            all_anns.append(r)
            img_counts[s] += 1
            cond_counts.update(r["conditions"])
            layout_counts[r["layout"]] += 1
            if r["record_id"] not in rec_ids_by_split[s]:
                fail(f"{r['image']}: record {r['record_id']} not in split {s}")
            ip = data / r["image"]
            if not ip.exists():
                missing += 1
                continue
            raw = ip.read_bytes()
            if hashlib.sha256(raw).hexdigest() != r["sha256"]:
                sha_bad += 1
            im = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
            if im is None or im.shape[1] != r["width"] or im.shape[0] != r["height"]:
                size_bad += 1
            for l in r["lines"]:
                ann_lines += 1
                vis = [w for w in l["words"] if w["visible_fraction"] >= VISIBLE_THRESHOLD]
                ann_words += len(l["words"])
                if l["text"] != " ".join(w["text"] for w in vis):
                    text_mismatch += 1
                for w in vis:
                    q = np.array(w["quad"])
                    if (q[:, 0].min() < -0.25 * (np.ptp(q[:, 0]) + 1) or q[:, 1].min() < -0.25 * (np.ptp(q[:, 1]) + 1)
                            or q[:, 0].max() > r["width"] * 1.0 + 0.25 * (np.ptp(q[:, 0]) + 1)
                            or q[:, 1].max() > r["height"] + 0.25 * (np.ptp(q[:, 1]) + 1)):
                        oob += 1
    report["images"] = dict(img_counts)
    report["conditions"] = dict(cond_counts)
    report["layouts"] = dict(layout_counts)
    report["annotations"] = {"lines": ann_lines, "words": ann_words, "visible_words_out_of_bounds": oob,
                             "line_text_mismatch": text_mismatch, "missing_images": missing,
                             "sha256_mismatch": sha_bad, "size_mismatch": size_bad}
    if missing and not a.allow_missing_images:
        fail(f"{missing} images referenced by annotations are missing")
    for k, v in (("sha256_mismatch", sha_bad), ("size_mismatch", size_bad), ("out_of_bounds", oob),
                 ("line_text_mismatch", text_mismatch)):
        if v:
            fail(f"{v} {k}")

    # ------------------------------------------------------------------ pixel agreement
    rng = random.Random(0)
    present = [r for r in all_anns if (data / r["image"]).exists()]
    sample = rng.sample(present, min(a.pixel_sample, len(present)))
    ok = checked = 0
    worst = []
    for r in sample:
        im = cv2.imread(str(data / r["image"]), cv2.IMREAD_GRAYSCALE)
        for l in r["lines"]:
            for w in l["words"]:
                if w["visible_fraction"] < 0.99 or "lighting" in " ".join(r["conditions"]):
                    continue
                q = np.array(w["quad"], np.float32)
                x0, y0 = np.floor(q.min(axis=0)).astype(int)
                x1, y1 = np.ceil(q.max(axis=0)).astype(int)
                x0, y0, x1, y1 = max(0, x0), max(0, y0), min(im.shape[1], x1), min(im.shape[0], y1)
                if x1 - x0 < 2 or y1 - y0 < 2:
                    continue
                inside = im[y0:y1, x0:x1].astype(np.float32)
                checked += 1
                # a real word has ink: noticeably more intensity variation than a flat patch
                if inside.std() >= 6.0:
                    ok += 1
                else:
                    worst.append((r["image"], w["text"], round(float(inside.std()), 2)))
    report["pixel_check"] = {"images": len(sample), "words_checked": checked,
                             "words_with_ink": ok, "share": round(ok / max(1, checked), 4),
                             "examples_without_ink": worst[:10]}
    if checked and ok / checked < 0.97:
        warn(f"only {ok / checked:.1%} of annotated words show ink in their box (heavy blur / low contrast?)")

    out = data / "validation_report.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("field_presence",)}, indent=2, ensure_ascii=False)[:6000])
    print(f"\n{'FAILED' if report['hard_failures'] else 'PASSED'}: {len(report['hard_failures'])} hard failures, "
          f"{len(report['warnings'])} warnings -> {out}")
    sys.exit(1 if report["hard_failures"] else 0)


if __name__ == "__main__":
    main()
