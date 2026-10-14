"""
Scan one or more label photographs from the command line and print the structured result (JSON).

    python scripts/analyze_label.py samples/real_world/maggi/back.jpg
    python scripts/analyze_label.py photo.jpg --category cosmetic --full      # everything incl. OCR lines
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+")
    ap.add_argument("--category", default="food")
    ap.add_argument("--side", default="front")
    ap.add_argument("--imported", action="store_true")
    ap.add_argument("--engine", choices=["ppocr", "hybrid", "tesseract"], default=None)
    ap.add_argument("--full", action="store_true", help="print OCR lines, raw passes and all fields too")
    a = ap.parse_args()
    from app.services import label_scan, preprocess
    for p in a.images:
        try:
            r = label_scan.scan_image(Path(p).read_bytes(), a.side, a.category, a.imported, a.engine)
        except preprocess.InvalidImage as exc:
            print(json.dumps({"image": p, "error": str(exc)}))
            continue
        if not a.full:
            r = {"image": p, "engine": r["engine"], "seconds": r["seconds"], "quality": r["image"]["quality"]["status"],
                 "ocr_text": r["ocr"]["full_text"], "structured": r["structured"], "warnings": r["warnings"],
                 "overall_status": r.get("overall_status"),
                 "potential_findings": [f"{f['check_id']}: {f['status']}" for f in r.get("potential_findings", [])]}
        print(json.dumps(r, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
