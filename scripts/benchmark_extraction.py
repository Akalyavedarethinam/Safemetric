"""
Run SafeMetric OCR against the synthetic real-world product fixtures.

Usage from the project root:
    python scripts/benchmark_extraction.py

This is a development benchmark, not a legal-compliance test.
"""
from pathlib import Path
import json
import sys

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services import ocr, preprocess, extraction, structured


def main():
    samples = ROOT / "samples" / "real_world"
    rows = []

    for product_dir in sorted(p for p in samples.iterdir() if p.is_dir()):
        for image_path in sorted(product_dir.glob("*.jpg")):
            bgr = preprocess.load_image(image_path.read_bytes())
            display, _ = preprocess.make_display_image(bgr)
            variants, scale, _ = preprocess.build_variants(display)
            result = ocr.run_ocr(variants, scale, display)
            fields = extraction.extract_fields([{
                "image_id": 1,
                "image_name": image_path.name,
                "side": "front" if image_path.stem == "front" else "back",
                "passes": result["passes"],
                "merged": result["lines"],
            }], product_dir.name)
            rows.append({
                "structured": structured.structured_output(fields),
                "product": product_dir.name,
                "image": image_path.name,
                "ocr_confidence": result["mean_confidence"],
                "word_count": result["word_count"],
                "net_quantity": fields["net_quantity"].value,
                "mrp": fields["mrp"].value,
                "manufacturer": fields["manufacturer_packer"].value,
                "mfg_date": fields["mfg_date"].value,
                "best_before": fields["best_before"].value,
            })

    out = samples / "benchmark_results.json"
    out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"Wrote {out}")
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
