"""
Tesseract OCR service.

* The Tesseract executable is configured via TESSERACT_CMD (pytesseract does NOT ship it).
* Several preprocessing variants x page-segmentation modes are OCR'd in parallel.
* Words keep their confidence and bounding boxes; lines are rebuilt from Tesseract's
  block/paragraph/line numbering.
* Results from all passes are merged: overlapping duplicate lines are removed, keeping the
  best-scoring reading, and the survivors are sorted into reading order.
All bounding boxes are expressed in DISPLAY-IMAGE pixel coordinates.
"""
from __future__ import annotations

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from .. import config

log = logging.getLogger("safemetric.ocr")


class OcrUnavailable(RuntimeError):
    pass


_version_cache: str | None = None


def _configure():
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD
    return pytesseract


def tesseract_status() -> dict:
    """Health information used by /api/health and before every analysis."""
    global _version_cache
    try:
        pt = _configure()
        if _version_cache is None:
            _version_cache = str(pt.get_tesseract_version())
        langs = []
        try:
            langs = pt.get_languages(config="")
        except Exception:
            pass
        return {"available": True, "version": _version_cache, "cmd": config.TESSERACT_CMD, "languages": langs}
    except Exception as exc:
        return {"available": False, "cmd": config.TESSERACT_CMD,
                "error": "Tesseract OCR is unavailable. Please configure TESSERACT_CMD.",
                "detail": str(exc)[:300], "exists": os.path.exists(config.TESSERACT_CMD)}


def ensure_tesseract() -> str:
    st = tesseract_status()
    if not st["available"]:
        raise OcrUnavailable(st["error"])
    return st["version"]


# ------------------------------------------------------------------ passes
# (variant, psm, description)
PASS_PLAN = [
    # Different segmentation modes matter on package panels: a front panel is
    # often a normal page, while a small batch/MRP block is sparse or single-line.
    ("clahe", 3, "CLAHE · automatic page segmentation"),
    ("lab_l", 6, "LAB luminance · uniform block"),
    ("hsv_v", 11, "HSV value · sparse text"),
    ("adaptive", 6, "Adaptive binary · uniform block"),
    ("otsu", 11, "Otsu binary · sparse text"),
    ("sharpen", 11, "Sharpened · sparse text"),
    ("lab_sharpen", 6, "LAB sharpened · uniform block"),
    ("channel_best", 6, "Best colour channel · uniform block"),
    ("inverted", 11, "Inverted · sparse text (light-on-dark)"),
    ("inverted_lab", 6, "Inverted LAB · uniform block"),
]

_JUNK = re.compile(r"^[\W_]+$")


def _bbox_union(boxes):
    x0 = min(b["x"] for b in boxes)
    y0 = min(b["y"] for b in boxes)
    x1 = max(b["x"] + b["width"] for b in boxes)
    y1 = max(b["y"] + b["height"] for b in boxes)
    return {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}


def _run_pass(image: np.ndarray, variant: str, psm: int, scale: float) -> dict:
    pt = _configure()
    cfg = f"--oem 1 --psm {psm} -c preserve_interword_spaces=1 -c user_defined_dpi=300"
    try:
        data = pt.image_to_data(image, lang=config.OCR_LANG, config=cfg,
                                output_type=pt.Output.DICT, timeout=config.OCR_PASS_TIMEOUT)
    except RuntimeError as exc:  # timeout
        log.warning("OCR pass %s/psm%s timed out: %s", variant, psm, exc)
        return {"variant": variant, "psm": psm, "lines": [], "error": "timeout"}
    inv = 1.0 / scale
    groups: dict[tuple, list] = {}
    for i, raw in enumerate(data["text"]):
        text = (raw or "").strip()
        conf = float(data["conf"][i])
        if not text or conf < 0:
            continue
        word = {
            "text": text,
            "confidence": round(conf, 1),
            "bbox": {"x": round(data["left"][i] * inv), "y": round(data["top"][i] * inv),
                     "width": max(1, round(data["width"][i] * inv)), "height": max(1, round(data["height"][i] * inv))},
        }
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        groups.setdefault(key, []).append(word)

    lines = []
    for words in groups.values():
        words.sort(key=lambda w: w["bbox"]["x"])
        text = " ".join(w["text"] for w in words)
        if _JUNK.match(text):
            continue
        alnum = sum(ch.isalnum() for ch in text)
        conf = float(np.mean([w["confidence"] for w in words]))
        if alnum == 0 or (conf < 25 and alnum < 4):
            continue
        lines.append({"text": text, "confidence": round(conf, 1), "bbox": _bbox_union([w["bbox"] for w in words]),
                      "words": words, "pass": f"{variant}/psm{psm}"})
    return {"variant": variant, "psm": psm, "lines": _reading_order(lines)}


def _reading_order(lines: list[dict]) -> list[dict]:
    lines = sorted(lines, key=lambda l: l["bbox"]["y"] + l["bbox"]["height"] / 2)
    rows: list[list[dict]] = []
    for l in lines:
        cy = l["bbox"]["y"] + l["bbox"]["height"] / 2
        if rows:
            last = rows[-1]
            rcy = np.mean([x["bbox"]["y"] + x["bbox"]["height"] / 2 for x in last])
            if abs(cy - rcy) < 0.45 * min(l["bbox"]["height"], min(x["bbox"]["height"] for x in last)):
                last.append(l)
                continue
        rows.append([l])
    return [l for row in rows for l in sorted(row, key=lambda x: x["bbox"]["x"])]


def _overlap(a: dict, b: dict) -> float:
    """Intersection over the smaller box (captures fragments inside a longer line)."""
    ax1, ay1 = a["x"] + a["width"], a["y"] + a["height"]
    bx1, by1 = b["x"] + b["width"], b["y"] + b["height"]
    iw = max(0, min(ax1, bx1) - max(a["x"], b["x"]))
    ih = max(0, min(ay1, by1) - max(a["y"], b["y"]))
    inter = iw * ih
    smaller = min(a["width"] * a["height"], b["width"] * b["height"]) or 1
    return inter / smaller


def _line_score(line: dict) -> float:
    """Rank OCR readings using confidence plus declaration usefulness.

    A high-confidence brand fragment should not automatically beat a slightly
    lower-confidence line that contains MRP / quantity / date information.
    """
    text = line["text"]
    alnum = sum(ch.isalnum() for ch in text)
    useful = len(re.findall(
        r"\b(?:MRP|NET|WT|WEIGHT|VOL|QUANTITY|MFG|MFD|PKD|BEST|USE|BEFORE|FSSAI|BATCH|LOT|"
        r"CONSUMER|CUSTOMER|CARE|INGREDIENTS|NUTRITION|IMPORTED|COUNTRY|USP|PRICE)\b", text, re.I))
    numeric_unit = bool(re.search(r"\d+\s*(?:kg|g|gm|ml|l|ltr|mg|n|nos|pcs|%|rs|inr|₹)", text, re.I))
    bonus = config.OCR_HYBRID_PPOCR_BONUS if line.get("engine") == "ppocr" else 0.0
    return line["confidence"] * (1 + 0.025 * min(alnum, 40)) + useful * 8 + (6 if numeric_unit else 0) + bonus


def merge_passes(passes: list[dict]) -> list[dict]:
    """Remove duplicate detections across passes, keeping the best reading of each region."""
    candidates = [l for p in passes for l in p["lines"]]
    candidates.sort(key=_line_score, reverse=True)
    kept: list[dict] = []
    for c in candidates:
        if any(_overlap(c["bbox"], k["bbox"]) > 0.55 for k in kept):
            continue
        kept.append(c)
    return _reading_order(kept)


def _clean_tesseract_lines(lines: list[dict]) -> list[dict]:
    """Word-level (length-preserving) clean-up of Tesseract output; the raw reading is kept."""
    from .textclean import clean_text
    if not config.OCR_TEXT_CLEAN:
        for l in lines:
            l["raw_text"] = l["text"]
            l.setdefault("engine", "tesseract")
        return lines
    for l in lines:
        raw = l["text"]
        for w in l["words"]:
            fixed = clean_text(w["text"])
            if fixed and " " not in fixed:
                w["text"] = fixed
        l["raw_text"] = raw
        l["text"] = " ".join(w["text"] for w in l["words"])
        l.setdefault("engine", "tesseract")
    return lines


def engine_label(engine: str | None = None) -> str:
    """Short human-readable engine description, e.g. 'PP-OCRv5 + Tesseract 5.3.4' (fits the DB column)."""
    engine = (engine or config.OCR_ENGINE)
    from . import ppocr
    pp = ppocr.status() if engine in ("hybrid", "ppocr") else {"available": False}
    tv = tesseract_status()
    parts = []
    if pp.get("available"):
        parts.append("PP-OCRv5" if "ppocrv5" in str(pp.get("rec_model", "")) else "PP-OCRv4")
    if (engine in ("hybrid", "tesseract") or not pp.get("available")) and tv.get("available"):
        parts.append(f"Tesseract {tv.get('version')}")
    return (" + ".join(parts) or "no OCR engine available")[:40]


def run_ocr(variants: dict[str, np.ndarray], scale: float, display_bgr: np.ndarray | None = None,
            engine: str | None = None) -> dict:
    """
    OCR one image and merge all passes.

    engine = hybrid    PP-OCR on the colour display image + the first OCR_HYBRID_TESSERACT_PASSES Tesseract passes
             ppocr     PP-OCR only
             tesseract original multi-pass Tesseract pipeline (all PASS_PLAN entries)
    Falls back to whichever engine is installed. Returns merged lines (+ per-pass data for debugging).
    """
    from . import ppocr
    engine = (engine or config.OCR_ENGINE)
    passes: list[dict] = []
    notes: list[str] = []
    use_pp = engine in ("hybrid", "ppocr") and display_bgr is not None and ppocr.available()
    if engine in ("hybrid", "ppocr") and not use_pp:
        notes.append("PP-OCR unavailable - Tesseract used")
    preprocessing: list[str] = []
    if use_pp:
        try:
            pl = ppocr.ocr_lines(display_bgr)
            preprocessing.append("PP-OCR text-line detection (DB) + recognition on the colour image, word fragments "
                                 "re-assembled into lines")
            if config.PPOCR_ENHANCE == "always" or (config.PPOCR_ENHANCE == "auto" and
                                                     (ppocr.needs_enhancement(display_bgr) or len(pl) < 4)):
                n_extra = sum(1 for l in pl if l.get("pass") == "ppocr_enhanced")
                preprocessing.append(f"Dark / low-contrast photo: second PP-OCR pass on a contrast-stretched + CLAHE "
                                     f"copy ({n_extra} line(s) taken from it)")
            passes.append({"variant": "colour", "psm": None, "engine": "ppocr", "lines": _reading_order(pl),
                           "description": "PP-OCR text-line detection + recognition (colour image)"})
        except Exception as exc:
            log.exception("PP-OCR pass failed")
            notes.append(f"PP-OCR pass failed: {exc}")
            use_pp = False
    run_tess = engine == "tesseract" or not use_pp or engine == "hybrid"
    if run_tess:
        if not tesseract_status()["available"]:
            if not use_pp:
                ensure_tesseract()          # raises OcrUnavailable with the friendly message
            notes.append("Tesseract unavailable - PP-OCR only")
        else:
            plan = [(v, psm, d) for v, psm, d in PASS_PLAN if v in variants]
            if use_pp and engine == "hybrid":
                plan = plan[:max(0, config.OCR_HYBRID_TESSERACT_PASSES)]
            preprocessing.append(f"Tesseract: {len(plan)} preprocessing variant x page-segmentation pass(es)")
            with ThreadPoolExecutor(max_workers=max(1, config.OCR_WORKERS)) as ex:
                futures = [ex.submit(_run_pass, variants[v], v, psm, scale) for v, psm, _ in plan]
                tpasses = [f.result() for f in futures]
            for p, (_, _, desc) in zip(tpasses, plan):
                p["description"] = desc
                p["engine"] = "tesseract"
                p["lines"] = _clean_tesseract_lines(p["lines"])
            if use_pp and engine == "hybrid":
                # Tesseract hallucinates "text" on textures / barcodes. In hybrid mode keep a Tesseract line only
                # if PP-OCR's detector also saw text there, or Tesseract itself is confident.
                pp_boxes = [l["bbox"] for p in passes if p.get("engine") == "ppocr" for l in p["lines"]]
                for p in tpasses:
                    p["lines"] = [l for l in p["lines"]
                                  if l["confidence"] >= 75 or any(_overlap(l["bbox"], b) > 0.3 for b in pp_boxes)]
            passes.extend(tpasses)
    if not passes:
        raise OcrUnavailable("No OCR engine is available. Install Tesseract or rapidocr_onnxruntime.")
    merged = merge_passes(passes)
    words = [w for l in merged for w in l["words"]]
    mean_conf = float(np.mean([w["confidence"] for w in words])) if words else 0.0
    return {
        "lines": merged,
        "passes": passes,
        "full_text": "\n".join(l["text"] for l in merged),
        "raw_text": "\n".join(l.get("raw_text", l["text"]) for l in merged),
        "mean_confidence": round(mean_conf, 1),
        "word_count": len(words),
        "engine": engine if use_pp or engine == "tesseract" else "tesseract",
        "notes": notes,
        "preprocessing": preprocessing,
        "tesseract_used": run_tess and tesseract_status()["available"],
    }
