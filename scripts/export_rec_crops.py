"""
Export rectified text-line crops + labels for fine-tuning a recogniser (PaddleOCR rec format:
"crops/<name>.jpg\t<text>"). Only visible, legible, fully-in-frame Latin lines are exported.

    python scripts/export_rec_crops.py --split train --out datasets/rec_crops
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "datasets"))
    ap.add_argument("--split", default="train")
    ap.add_argument("--out", default=str(ROOT / "datasets" / "rec_crops"))
    ap.add_argument("--height", type=int, default=48)
    a = ap.parse_args()
    data, out = Path(a.data), Path(a.out) / a.split
    (out / "crops").mkdir(parents=True, exist_ok=True)
    n = 0
    with open(out / "rec_gt.txt", "w", encoding="utf-8") as fo:
        for line in open(data / f"ocr_annotations/{a.split}.jsonl", encoding="utf-8"):
            r = json.loads(line)
            img = cv2.imread(str(data / r["image"]))
            if img is None:
                continue
            for k, l in enumerate(r["lines"]):
                if not (l["visible"] and l["legible"] and not l["partial"] and l["text"]) or re.search(r"[ऀ-ॿ]", l["text"]):
                    continue
                q = np.float32(l["quad"])
                w = int(max(np.linalg.norm(q[1] - q[0]), np.linalg.norm(q[2] - q[3])))
                h = int(max(np.linalg.norm(q[3] - q[0]), np.linalg.norm(q[2] - q[1])))
                if w < 4 or h < 4:
                    continue
                M = cv2.getPerspectiveTransform(q, np.float32([[0, 0], [w, 0], [w, h], [0, h]]))
                crop = cv2.warpPerspective(img, M, (w, h), borderMode=cv2.BORDER_REPLICATE)
                s = a.height / h
                crop = cv2.resize(crop, (max(1, int(w * s)), a.height))
                name = f"{Path(r['image']).stem}_{k:03d}.jpg"
                cv2.imwrite(str(out / "crops" / name), crop)
                fo.write(f"crops/{name}\t{l['text']}\n")
                n += 1
    print(f"{n} crops -> {out}")


if __name__ == "__main__":
    main()
