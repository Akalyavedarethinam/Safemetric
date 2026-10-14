"""
Build the release ZIP (LegalMetrologyProject.zip) and verify its contents.

    python scripts/package_release.py --out ../LegalMetrologyProject.zip [--train-images 200] [--all-images]

Included: source code, prebuilt UI, models, datasets (all JSONL + val/test images + a sample of train images,
unless --all-images), generator, training and evaluation code, results, docs.
Excluded: node_modules, caches, runtime data (backend/data: DB, uploads), .env files, previews, secrets.
"""
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOP = "LegalMetrologyProject"
EXCLUDE_DIRS = {"node_modules", "__pycache__", ".pytest_cache", ".venv", "venv", ".git", "_preview", "rec_crops"}
EXCLUDE_FILES = {".env", "tsconfig.tsbuildinfo", ".DS_Store"}
REQUIRED = ["frontend/src", "frontend/dist/index.html", "backend/app/main.py", "backend/app/services/ppocr.py",
            "backend/requirements.txt", "datasets/synthetic_text", "datasets/product_label_images/test",
            "datasets/ocr_annotations/test.jsonl", "datasets/field_extraction/test.jsonl", "datasets/README.md",
            "models/ocr/ppocrv5/det.onnx", "models/ocr/ppocrv5/rec.onnx", "models/extraction/line_role_model.npz",
            "training/datagen/render.py", "training/train_line_roles.py", "evaluation/evaluate_ocr.py",
            "evaluation/results/SUMMARY.md", "scripts/generate_datasets.py", "requirements.txt", "README.md",
            "TRAINING_GUIDE.md", "PROJECT_REPORT.md"]


def wanted(rel: Path, train_keep: set[str], all_images: bool) -> bool:
    if any(p in EXCLUDE_DIRS for p in rel.parts) or rel.name in EXCLUDE_FILES:
        return False
    if rel.parts[:2] == ("backend", "data"):
        return False
    if rel.suffix == ".zip":
        return False
    if rel.parts[:3] == ("datasets", "product_label_images", "train") and not all_images:
        return rel.name in train_keep
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT.parent / "LegalMetrologyProject.zip"))
    ap.add_argument("--train-images", type=int, default=200)
    ap.add_argument("--all-images", action="store_true")
    a = ap.parse_args()
    missing = [r for r in REQUIRED if not (ROOT / r).exists()]
    if missing:
        raise SystemExit(f"missing required files: {missing}")
    train_ann = ROOT / "datasets" / "ocr_annotations" / "train.jsonl"
    keep = set()
    with open(train_ann, encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if i >= a.train_images:
                break
            keep.add(Path(json.loads(line)["image"]).name)
    n = size = 0
    out = Path(a.out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(ROOT.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(ROOT)
            if not wanted(rel, keep, a.all_images):
                continue
            ctype = zipfile.ZIP_STORED if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".onnx", ".npz") else zipfile.ZIP_DEFLATED
            z.write(p, f"{TOP}/{rel.as_posix()}", compress_type=ctype)
            n += 1
            size += p.stat().st_size
    with zipfile.ZipFile(out) as z:
        names = set(z.namelist())
        bad = [x for x in names if any(s in x for s in ("/node_modules/", "__pycache__", "/backend/data/", "/.env"))
               and not x.endswith(".env.example")]
        for r in REQUIRED:
            if not any(x.startswith(f"{TOP}/{r}") for x in names):
                raise SystemExit(f"verification failed: {r} not in zip")
        if bad:
            raise SystemExit(f"verification failed: excluded files present: {bad[:5]}")
        z.testzip()
    print(f"{out}: {n} files, {size / 1e6:.1f} MB uncompressed, {out.stat().st_size / 1e6:.1f} MB zipped - verified")


if __name__ == "__main__":
    main()
