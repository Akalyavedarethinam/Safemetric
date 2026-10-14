"""
Draw ground-truth line / word quads on dataset images so annotations can be checked by eye.

    python scripts/visualize_annotations.py --split test --n 12 --out datasets/_preview
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
COLORS = {"brand_name": (0, 0, 255), "product_name": (0, 128, 255), "net_quantity": (0, 200, 0), "mrp": (255, 0, 255),
          "batch_number": (255, 128, 0), "mfg_date": (200, 200, 0), "packed_on": (200, 200, 0), "expiry_date": (0, 200, 200),
          "best_before": (0, 200, 200), "manufacturer_name": (128, 0, 128), "manufacturer_address": (128, 64, 128),
          "customer_care": (0, 100, 0), "fssai_license": (100, 0, 0), "watermark": (128, 128, 128)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "datasets"))
    ap.add_argument("--split", default="test")
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--words", action="store_true", help="draw word boxes too")
    ap.add_argument("--out", default=str(ROOT / "datasets" / "_preview"))
    a = ap.parse_args()
    data, out = Path(a.data), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(l) for l in open(data / f"ocr_annotations/{a.split}.jsonl", encoding="utf-8")][a.start:a.start + a.n]
    for r in rows:
        img = cv2.imread(str(data / r["image"]))
        for l in r["lines"]:
            c = COLORS.get(l["field"], (60, 60, 60)) if l["visible"] else (0, 0, 0)
            q = np.array(l["quad"], np.int32)
            cv2.polylines(img, [q], True, c, 2)
            if a.words:
                for w in l["words"]:
                    cv2.polylines(img, [np.array(w["quad"], np.int32)], True, (0, 255, 255), 1)
        cv2.putText(img, ",".join(r["conditions"])[:80], (5, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2)
        cv2.imwrite(str(out / Path(r["image"]).name), img)
    print(f"wrote {len(rows)} previews to {out}")


if __name__ == "__main__":
    main()
