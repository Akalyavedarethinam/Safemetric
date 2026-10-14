"""
Generate the SafeMetric SYNTHETIC Legal Metrology label datasets.

    python scripts/generate_datasets.py                       # default sizes (12,000 records / 2,400 images)
    python scripts/generate_datasets.py --records 50000 --images 10000 --workers 8
    python scripts/generate_datasets.py --records 500 --images 60 --out /tmp/ds   # quick smoke test

Output (under --out, default: datasets/):
    synthetic_text/records_{train,val,test}.jsonl      full label records (fields, panels, defects)
    synthetic_text/text_lines_{split}.jsonl            one printed line per row, tagged with its field
    product_label_images/{split}/syn_NNNNNN.jpg         rendered + degraded label photographs
    ocr_annotations/{split}.jsonl                      image -> lines/words (quads, bboxes, text, field tags)
    ocr_annotations/ppocr_det_{split}.txt              same boxes in PaddleOCR detection-label format
    field_extraction/{split}.jsonl                     OCR-like text (4 noise levels) -> expected structured fields
    manifest.json                                      counts, seed, generator version, SHA-256 of every file

Everything is deterministic for a given --seed: record i and image i are generated from their own
seeded RNG, so the same command reproduces byte-identical files (and more workers do not change them).
All data is synthetic; every image carries a visible watermark plus EXIF/COM metadata saying so.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import time
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training.datagen import canonical, noise, records, render  # noqa: E402

SPLITS = ("train", "val", "test")
NOISE_LEVELS = ("clean", "light", "medium", "heavy")
_BRANDS = None


def _brands():
    global _BRANDS
    if _BRANDS is None:
        _BRANDS = records.brand_pool()
    return _BRANDS


# ------------------------------------------------------------------------------ workers
def build_record(args):
    i, seed = args
    rec = records.make_record(i, seed, _brands())
    rng = random.Random(f"{seed}:fx:{i}")
    lines = [{**l, "panel": p} for p in ("front", "back") for l in rec["panels"][p]]
    fx = []
    level = NOISE_LEVELS[i % len(NOISE_LEVELS)]
    noisy, dropped = noise.noisy_lines(lines, level, rng)
    expected = {k: v for k, v in canonical.expected_flat(rec["fields"]).items() if not _dropped(k, dropped)}
    fx.append({"id": f"{rec['id']}_fx", "record_id": rec["id"], "split": rec["split"], "synthetic": True,
               "source": "ground_truth_text_with_synthetic_ocr_noise", "noise_level": level,
               "category": rec["category"], "app_category": rec["app_category"], "imported": rec["imported"],
               "lines": [{"text": l["text"], "size": l["size"], "panel": l["panel"], "field": l["field"]} for l in noisy],
               "input_text": "\n".join(l["text"] for l in noisy), "expected": expected,
               "dropped_fields": sorted(dropped)})
    text_lines = [{"record_id": rec["id"], "split": rec["split"], "synthetic": True, "panel": l["panel"], "text": l["text"],
                   "field": l["field"], "fields": l["fields"], "size": l["size"], "lang": l["lang"], "category": rec["category"]}
                  for l in lines]
    return rec, fx, text_lines


_FIELD_OF_LINE = {"manufacturer_name": ("manufacturer_name",), "manufacturer_address": ("manufacturer_address",),
                  "customer_care": ("customer_care",), "net_quantity": ("net_quantity",), "mrp": ("mrp",)}


def _dropped(k, dropped):
    return k in dropped


def build_image(args):
    i, seed, out_dir = args
    rec = records.make_record(i, seed, _brands())
    rng = random.Random(f"{seed}:img:{i}")
    heldout = rec["split"] == "test" and rng.random() < 0.35
    label, placed, meta = render.render_label(rec, rng, heldout)
    img, lines, cond = render.compose_and_degrade(label, placed, rng, meta["base_font_px"])
    tags = render.condition_tags(meta, cond)
    rel = f"product_label_images/{rec['split']}/{rec['id']}.jpg"
    comment = records.SYNTHETIC_NOTICE + f" id={rec['id']}"
    data = render.encode_jpeg(img, cond["jpeg_quality"], comment)
    path = Path(out_dir) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)

    # fields fully visible in THIS image (a front-only photo cannot show the manufacturer, etc.)
    present, broken = set(), set()
    for ln in lines:
        for f in ln["fields"]:
            present.add(f)
            if not ln["visible"] or ln["partial"] or not ln["legible"]:
                broken.add(f)
    # the rendered text may have replaced ₹ by Rs. (font without the glyph); values are unchanged
    expected = {k: v for k, v in canonical.expected_flat(rec["fields"]).items()
                if k in present and k not in broken}
    visible = [l for l in lines if l["visible"]]
    ann = {
        "image": rel, "record_id": rec["id"], "split": rec["split"], "synthetic": True,
        "width": int(img.shape[1]), "height": int(img.shape[0]), "sha256": hashlib.sha256(data).hexdigest(),
        "category": rec["category"], "app_category": rec["app_category"], "imported": rec["imported"],
        "defects": rec["defects"], "layout": meta["layout"], "font_family": meta["font_family"],
        "display_font_family": meta["display_font_family"], "heldout_font": meta["heldout_font"],
        "color_style": meta["color_style"], "conditions": tags, "augmentation": cond,
        "lines": lines, "gt_text": "\n".join(l["text"] for l in visible if l["text"]),
        "legible_line_share": round(sum(l["legible"] for l in visible) / max(1, len(visible)), 3),
        "expected_fields": expected,
        "fields_not_fully_visible": sorted((set(canonical.expected_flat(rec["fields"])) & broken)),
    }
    ppocr = [{"transcription": l["text"] if l["visible"] and l["legible"] and not l["partial"] else "###",
              "points": [[round(x), round(y)] for x, y in l["quad"]]} for l in lines if l["text"] or l["partial"]]
    return ann, f"{rel}\t{json.dumps(ppocr, ensure_ascii=False)}"


# ------------------------------------------------------------------------------ main
def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--records", type=int, default=12000)
    ap.add_argument("--images", type=int, default=2400, help="images rendered for records 0..N-1")
    ap.add_argument("--seed", type=int, default=20260924)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2)))
    ap.add_argument("--out", default=str(ROOT / "datasets"))
    ap.add_argument("--skip-images", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    for sub in ("synthetic_text", "ocr_annotations", "field_extraction", "product_label_images"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    with Pool(a.workers) as pool:
        recs = pool.map(build_record, [(i, a.seed) for i in range(a.records)], chunksize=64)
    fh = {s: open(out / f"synthetic_text/records_{s}.jsonl", "w", encoding="utf-8") for s in SPLITS}
    fl = {s: open(out / f"synthetic_text/text_lines_{s}.jsonl", "w", encoding="utf-8") for s in SPLITS}
    ff = {s: open(out / f"field_extraction/{s}.jsonl", "w", encoding="utf-8") for s in SPLITS}
    counts = Counter()
    for rec, fx, tl in recs:
        s = rec["split"]
        fh[s].write(json.dumps(rec, ensure_ascii=False) + "\n")
        counts[f"records_{s}"] += 1
        for x in fx:
            ff[s].write(json.dumps(x, ensure_ascii=False) + "\n")
            counts[f"field_examples_{s}"] += 1
        for x in tl:
            fl[s].write(json.dumps(x, ensure_ascii=False) + "\n")
            counts[f"text_lines_{s}"] += 1
    for f in (*fh.values(), *fl.values(), *ff.values()):
        f.close()
    print(f"records: {a.records} in {time.time() - t0:.1f}s")

    if not a.skip_images and a.images:
        t1 = time.time()
        fa = {s: open(out / f"ocr_annotations/{s}.jsonl", "w", encoding="utf-8") for s in SPLITS}
        fd = {s: open(out / f"ocr_annotations/ppocr_det_{s}.txt", "w", encoding="utf-8") for s in SPLITS}
        with Pool(a.workers) as pool:
            for n, (ann, det) in enumerate(pool.imap(build_image, [(i, a.seed, str(out)) for i in range(a.images)], chunksize=8)):
                s = ann["split"]
                fa[s].write(json.dumps(ann, ensure_ascii=False) + "\n")
                fd[s].write(det + "\n")
                counts[f"images_{s}"] += 1
                counts[f"line_annotations_{s}"] += len(ann["lines"])
                counts[f"word_annotations_{s}"] += sum(len(l["words"]) for l in ann["lines"])
                if (n + 1) % 200 == 0:
                    print(f"  images {n + 1}/{a.images}  ({time.time() - t1:.0f}s)", flush=True)
        for f in (*fa.values(), *fd.values()):
            f.close()
        print(f"images: {a.images} in {time.time() - t1:.1f}s")

    files = {}
    for p in sorted(out.rglob("*")):
        if p.is_file() and p.name != "manifest.json" and "product_label_images" not in p.parts:
            files[str(p.relative_to(out))] = {"bytes": p.stat().st_size, "sha256": _sha(p)}
    manifest = {
        "name": "SafeMetric synthetic Legal Metrology label dataset",
        "synthetic": True, "notice": records.SYNTHETIC_NOTICE,
        "generator_version": records.GENERATOR_VERSION, "seed": a.seed,
        "command": " ".join(["python", "scripts/generate_datasets.py", f"--records {a.records}", f"--images {a.images}",
                             f"--seed {a.seed}"]),
        "split_policy": "group split by brand (sha256 of brand name): 70/15/15; test also uses 3 held-out font families",
        "counts": dict(sorted(counts.items())),
        "files": files,
        "images_sha256_in": "ocr_annotations/<split>.jsonl (field 'sha256' per image)",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest["counts"], indent=2))
    print(f"total {time.time() - t0:.1f}s -> {out}")


if __name__ == "__main__":
    main()
