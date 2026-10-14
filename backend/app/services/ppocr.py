"""
PP-OCR text DETECTION + RECOGNITION (PaddleOCR models, run with ONNX Runtime via rapidocr_onnxruntime).

Why it was added (measured, see PROJECT_REPORT.md): Tesseract's page segmentation fails on rotated,
perspective-distorted and small / blurred package text. PP-OCR's DB detector finds each text line as a
rotated quadrilateral, and each line is rectified before recognition, so orientation and layout matter
much less.

Models: `models/ocr/ppocrv5/{det,rec}.onnx` (PP-OCRv5 mobile) when present, otherwise the PP-OCRv4 models
bundled inside the rapidocr_onnxruntime wheel. Everything runs offline on CPU.

Public API
  available() / status()
  estimate_geometry(bgr)  -> dominant text angle + 180° decision (used to straighten the display image)
  ocr_lines(bgr)          -> lines in SafeMetric's OCR line format (text, raw_text, confidence, bbox,
                             quad, words[...]) in `bgr` pixel coordinates
"""
from __future__ import annotations

import logging
import math
import threading
from pathlib import Path

import cv2
import numpy as np

from .. import config
from .textclean import clean_text

log = logging.getLogger("safemetric.ppocr")

_engine = None
_engine_error: str | None = None
_lock = threading.Lock()
_run_lock = threading.Lock()          # onnxruntime sessions are thread-safe, but CPU is better used serially


def _model_paths() -> dict:
    d = Path(config.PPOCR_MODEL_DIR)
    out = {}
    if (d / "det.onnx").exists():
        out["det_model_path"] = str(d / "det.onnx")
    if (d / "rec.onnx").exists():
        out["rec_model_path"] = str(d / "rec.onnx")
    return out


def get_engine():
    global _engine, _engine_error
    if _engine is not None or _engine_error is not None:
        return _engine
    with _lock:
        if _engine is None and _engine_error is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
                _engine = RapidOCR(**_model_paths())
            except Exception as exc:          # package missing or model file unreadable
                _engine_error = f"{type(exc).__name__}: {exc}"
                log.warning("PP-OCR engine unavailable: %s", _engine_error)
    return _engine


def available() -> bool:
    return get_engine() is not None


def status() -> dict:
    eng = get_engine()
    paths = _model_paths()
    if eng is None:
        return {"available": False, "error": _engine_error or "not loaded"}
    try:
        import rapidocr_onnxruntime
        ver = getattr(rapidocr_onnxruntime, "__version__", "")
    except Exception:
        ver = ""
    return {"available": True, "runtime": f"rapidocr_onnxruntime {ver}".strip(),
            "det_model": Path(paths["det_model_path"]).parent.name + "/det.onnx" if "det_model_path" in paths else "PP-OCRv4 (bundled)",
            "rec_model": Path(paths["rec_model_path"]).parent.name + "/rec.onnx" if "rec_model_path" in paths else "PP-OCRv4 (bundled)"}


# ------------------------------------------------------------------------------ low-level helpers
def _order_quad(q: np.ndarray) -> np.ndarray:
    return np.asarray(q, np.float32).reshape(4, 2)


def _crop(img: np.ndarray, quad: np.ndarray) -> np.ndarray:
    eng = get_engine()
    return eng.get_crop_img_list(img, [quad.astype(np.float32)])[0]


def _detect(img: np.ndarray) -> list[np.ndarray]:
    eng = get_engine()
    boxes, _ = eng.text_det(img)
    if boxes is None or len(boxes) == 0:
        return []
    return [_order_quad(b) for b in boxes]


def _recognize(crops: list[np.ndarray]) -> list[tuple[str, float]]:
    if not crops:
        return []
    eng = get_engine()
    res, _ = eng.text_rec(crops, False)
    return [(r[0], float(r[1])) for r in res]


# ------------------------------------------------------------------------------ page geometry
def _line_angle(q: np.ndarray) -> tuple[float, float, float]:
    """(angle_deg of the text direction in (-90, 90], long side, short side)."""
    e1 = q[1] - q[0]
    e2 = q[3] - q[0]
    l1, l2 = float(np.hypot(*e1)), float(np.hypot(*e2))
    v = e1 if l1 >= l2 else e2
    ang = math.degrees(math.atan2(float(v[1]), float(v[0])))
    while ang <= -90:
        ang += 180
    while ang > 90:
        ang -= 180
    return ang, max(l1, l2), min(l1, l2)


def estimate_geometry(bgr: np.ndarray, max_side: int = 1280) -> dict | None:
    """
    Find the rotation (counter-clockwise, degrees, any angle) that makes the text horizontal and upright.
      1. detect text lines on a reduced copy; take the length-weighted dominant direction of elongated boxes
      2. rotate by that angle, then recognise the largest lines both as-is and turned 180°: the orientation
         with the clearly higher recognition confidence wins
    Returns None when too little text is found (caller falls back to Tesseract OSD).
    """
    if not available():
        return None
    h, w = bgr.shape[:2]
    s = min(1.0, max_side / max(h, w))
    small = cv2.resize(bgr, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA) if s < 1 else bgr
    with _run_lock:
        quads = _detect(small)
    cand = []
    for q in quads:
        ang, long_, short = _line_angle(q)
        if long_ >= 2.2 * max(short, 1) and long_ > 20:
            cand.append((ang, long_))
    if len(cand) < 2:
        return None
    # circular (mod 180) weighted histogram, 1° bins, smoothed
    hist = np.zeros(180)
    for ang, wgt in cand:
        hist[int(round(ang)) % 180] += wgt
    sm = np.convolve(np.concatenate([hist[-3:], hist, hist[:3]]), np.ones(7) / 7, mode="same")[3:-3]
    peak = int(np.argmax(sm))
    near = [(a, wt) for a, wt in cand if min(abs((round(a) - peak) % 180), 180 - abs((round(a) - peak) % 180)) <= 6]
    ref = peak if peak <= 90 else peak - 180
    angs = np.array([a if abs(a - ref) <= 90 else (a - 180 if a > ref else a + 180) for a, _ in near])
    wts = np.array([wt for _, wt in near])
    order = np.argsort(angs)
    cum = np.cumsum(wts[order])
    angle = float(angs[order][np.searchsorted(cum, cum[-1] / 2)])
    share = float(wts.sum() / sum(wt for _, wt in cand))

    # 0° vs 180° decision on the straightened image
    rot, _ = rotate_expand(small, angle)
    M = _rotation_matrix(small.shape[1], small.shape[0], angle)
    big = sorted(quads, key=lambda q: -_line_angle(q)[1])[:10]
    crops_up, crops_dn = [], []
    for q in big:
        tq = cv2.perspectiveTransform(q.reshape(1, 4, 2).astype(np.float32), M)[0]
        tq = _rect_quad(tq)
        c = _crop(rot, tq)
        if c.size == 0 or c.shape[0] < 6 or c.shape[1] < 6:
            continue
        crops_up.append(c)
        crops_dn.append(cv2.rotate(c, cv2.ROTATE_180))
    with _run_lock:
        up = _recognize(crops_up)
        dn = _recognize(crops_dn)
    su = float(np.mean([sc * min(len(t), 20) for t, sc in up])) if up else 0.0
    sd = float(np.mean([sc * min(len(t), 20) for t, sc in dn])) if dn else 0.0
    flip = sd > su * 1.15 and sd - su > 1.0
    total = angle + (180.0 if flip else 0.0)
    if total > 180:
        total -= 360
    return {"angle": round(total, 2), "text_angle": round(angle, 2), "flipped": flip, "lines": len(quads),
            "dominant_share": round(share, 3), "upright_score": round(su, 2), "flipped_score": round(sd, 2)}


def _rect_quad(q: np.ndarray) -> np.ndarray:
    """Axis-aligned rectangle around a (now nearly horizontal) quad, in tl,tr,br,bl order."""
    x0, y0 = q.min(axis=0)
    x1, y1 = q.max(axis=0)
    return np.float32([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])


def _rotation_matrix(w: int, h: int, angle_ccw: float) -> np.ndarray:
    """3x3 matrix of a counter-clockwise rotation about the centre with the canvas expanded to fit."""
    a = angle_ccw % 360
    if abs(a - round(a / 90) * 90) < 1e-6:
        k = int(round(a / 90)) % 4
        if k == 0:
            return np.eye(3)
        if k == 1:      # 90° CCW
            return np.array([[0, 1, 0], [-1, 0, w - 1], [0, 0, 1]], np.float64)
        if k == 2:
            return np.array([[-1, 0, w - 1], [0, -1, h - 1], [0, 0, 1]], np.float64)
        return np.array([[0, -1, h - 1], [1, 0, 0], [0, 0, 1]], np.float64)       # 270° CCW = 90° CW
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle_ccw, 1.0)
    cos, sin = abs(m[0, 0]), abs(m[0, 1])
    nw, nh = int(h * sin + w * cos), int(h * cos + w * sin)
    m[0, 2] += nw / 2 - w / 2
    m[1, 2] += nh / 2 - h / 2
    return np.vstack([m, [0, 0, 1]])


def rotate_expand(bgr: np.ndarray, angle_ccw: float) -> tuple[np.ndarray, np.ndarray]:
    """Rotate counter-clockwise by any angle, expanding the canvas. Returns (image, 3x3 matrix orig->new)."""
    h, w = bgr.shape[:2]
    M = _rotation_matrix(w, h, angle_ccw)
    a = angle_ccw % 360
    if abs(a - round(a / 90) * 90) < 1e-6:
        k = int(round(a / 90)) % 4
        img = bgr if k == 0 else cv2.rotate(bgr, {1: cv2.ROTATE_90_COUNTERCLOCKWISE, 2: cv2.ROTATE_180,
                                                  3: cv2.ROTATE_90_CLOCKWISE}[k])
        return img, M
    cos, sin = abs(M[0, 0]), abs(M[0, 1])
    nw, nh = int(h * sin + w * cos), int(h * cos + w * sin)
    img = cv2.warpAffine(bgr, M[:2], (nw, nh), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return img, M


# ------------------------------------------------------------------------------ OCR
def enhance_for_ocr(bgr: np.ndarray) -> np.ndarray:
    """Percentile contrast stretch + CLAHE on the LAB lightness channel (colours kept)."""
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    L = lab[..., 0].astype(np.float32)
    lo, hi = np.percentile(L, 1), np.percentile(L, 99)
    L = np.clip((L - lo) * 255.0 / max(hi - lo, 1.0), 0, 255).astype(np.uint8)
    lab[..., 0] = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(L)
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def blur_score(bgr: np.ndarray) -> float:
    return float(cv2.Laplacian(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())


def sharpen_upscale(bgr: np.ndarray, factor: float) -> np.ndarray:
    """Upscale (cubic) and unsharp-mask a blurred photo so thin, soft strokes become separable."""
    up = cv2.resize(bgr, None, fx=factor, fy=factor, interpolation=cv2.INTER_CUBIC)
    soft = cv2.GaussianBlur(up, (0, 0), 1.6 * factor)
    return cv2.addWeighted(up, 2.0, soft, -1.0, 0)


def _scale_lines(lines: list[dict], f: float) -> list[dict]:
    def sb(b):
        return {"x": int(round(b["x"] * f)), "y": int(round(b["y"] * f)), "width": max(1, int(round(b["width"] * f))),
                "height": max(1, int(round(b["height"] * f)))}
    for l in lines:
        l["bbox"] = sb(l["bbox"])
        l["quad"] = [[round(x * f, 1), round(y * f, 1)] for x, y in l["quad"]]
        for w in l["words"]:
            w["bbox"] = sb(w["bbox"])
    return lines


def needs_enhancement(bgr: np.ndarray) -> bool:
    L = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)[..., 0]
    return float(L.mean()) < 110 or float(L.std()) < 40


def _inter_small(a: dict, b: dict) -> float:
    ax1, ay1, bx1, by1 = a["x"] + a["width"], a["y"] + a["height"], b["x"] + b["width"], b["y"] + b["height"]
    iw = max(0, min(ax1, bx1) - max(a["x"], b["x"]))
    ih = max(0, min(ay1, by1) - max(a["y"], b["y"]))
    return iw * ih / max(1, min(a["width"] * a["height"], b["width"] * b["height"]))


def _iou(a: dict, b: dict) -> float:
    ax1, ay1, bx1, by1 = a["x"] + a["width"], a["y"] + a["height"], b["x"] + b["width"], b["y"] + b["height"]
    iw = max(0, min(ax1, bx1) - max(a["x"], b["x"]))
    ih = max(0, min(ay1, by1) - max(a["y"], b["y"]))
    inter = iw * ih
    return inter / max(1, a["width"] * a["height"] + b["width"] * b["height"] - inter)


def _merge_pp(base: list[dict], extra: list[dict]) -> list[dict]:
    """Add lines found only in the enhanced pass. Where both passes read the SAME extent (IoU >= 0.6) keep the
    more confident reading; a fragment of an existing line never replaces the whole line."""
    out = list(base)
    for e in extra:
        over = [i for i, b in enumerate(out) if _inter_small(e["bbox"], b["bbox"]) > 0.5]
        if not over:
            out.append(e)
            continue
        same = [i for i in over if _iou(e["bbox"], out[i]["bbox"]) >= 0.6]
        if len(same) == 1 and e["confidence"] > out[same[0]]["confidence"] + 2:
            out[same[0]] = e
    return merge_row_fragments(out)


def ocr_lines(bgr: np.ndarray, use_cls: bool | None = None, min_score: float | None = None) -> list[dict]:
    """PP-OCR on the image, plus (PPOCR_ENHANCE=auto) a second pass on a contrast-enhanced copy for dark /
    low-contrast photographs or when very little text was found. Coordinates are in `bgr` pixels."""
    lines = merge_row_fragments(_ocr_once(bgr, use_cls, min_score))
    mode = config.PPOCR_ENHANCE
    if mode == "always" or (mode == "auto" and (len(lines) < 4 or needs_enhancement(bgr))):
        extra = merge_row_fragments(_ocr_once(enhance_for_ocr(bgr), use_cls, min_score))
        for l in extra:
            l["pass"] = "ppocr_enhanced"
        lines = _merge_pp(lines, extra)
    dmode = config.PPOCR_DEBLUR
    if dmode == "always" or (dmode == "auto" and blur_score(bgr) < config.PPOCR_BLUR_THRESHOLD):
        f = 2.0 if max(bgr.shape[:2]) <= 2000 else 1.25
        extra = _scale_lines(merge_row_fragments(_ocr_once(sharpen_upscale(bgr, f), use_cls, min_score)), 1 / f)
        for l in extra:
            l["pass"] = "ppocr_sharpened"
        lines = _merge_pp(lines, extra)
    return lines


def _ocr_once(bgr: np.ndarray, use_cls: bool | None = None, min_score: float | None = None) -> list[dict]:
    """
    Detect + recognise all text lines. Returned coordinates are in `bgr` pixels.
    `use_cls` enables PP-OCR's per-line 180° classifier - off by default because the page has already been
    turned upright by estimate_geometry() and the classifier occasionally flips correct lines.
    """
    eng = get_engine()
    if eng is None:
        return []
    use_cls = config.PPOCR_USE_CLS if use_cls is None else use_cls
    min_score = config.PPOCR_MIN_SCORE if min_score is None else min_score
    with _run_lock:
        eng.text_det.limit_side_len = config.PPOCR_DET_LIMIT
        res, _ = eng(bgr, use_cls=use_cls, return_word_box=True, text_score=min_score,
                     box_thresh=config.PPOCR_BOX_THRESH, unclip_ratio=config.PPOCR_UNCLIP)
    lines = []
    for item in res or []:
        quad = np.asarray(item[0], np.float32).reshape(4, 2)
        raw, score = str(item[1]), float(item[2])
        char_boxes = item[3] if len(item) > 3 else None
        chars = item[4] if len(item) > 4 else None
        char_conf = item[5] if len(item) > 5 else None
        text = clean_text(raw) if config.OCR_TEXT_CLEAN else raw
        if not text.strip():
            continue
        words = _words(text, raw, quad, char_boxes, chars, char_conf, score)
        x0, y0 = quad.min(axis=0)
        x1, y1 = quad.max(axis=0)
        lines.append({
            "text": text, "raw_text": raw, "confidence": round(score * 100, 1),
            "bbox": {"x": int(round(x0)), "y": int(round(y0)), "width": max(1, int(round(x1 - x0))),
                     "height": max(1, int(round(y1 - y0)))},
            "quad": quad.round(1).tolist(), "words": words, "pass": "ppocr", "engine": "ppocr",
        })
    return lines


def merge_row_fragments(lines: list[dict], max_gap: float = 1.6) -> list[dict]:
    """
    The DB detector sometimes returns each WORD of large, widely spaced text as its own box
    ("GOLDEN" "MILL", "Net" "Wt." "approx" "500" "gms"). Re-assemble text lines: fragments on the same
    baseline (vertical overlap >= 60 %, similar height) separated by less than `max_gap` x text height are joined.
    Wider gaps (table columns, two panels side by side) are left alone.
    """
    if len(lines) < 2:
        return lines
    rest = sorted(lines, key=lambda l: (l["bbox"]["x"], l["bbox"]["y"]))
    used = [False] * len(rest)
    out = []

    def joinable(a: dict, b: dict) -> float | None:
        """gap (in px) if b continues a to the right on the same text line, else None"""
        ab, bb = a["bbox"], b["bbox"]
        h = min(ab["height"], bb["height"])
        if not 0.6 <= bb["height"] / max(1, ab["height"]) <= 1.67:
            return None
        vov = min(ab["y"] + ab["height"], bb["y"] + bb["height"]) - max(ab["y"], bb["y"])
        gap = bb["x"] - (ab["x"] + ab["width"])
        centre_order = (bb["x"] + bb["width"] / 2) > (ab["x"] + ab["width"] / 2)
        if vov >= 0.6 * h and centre_order and -0.8 * h <= gap <= max_gap * h:
            return gap
        return None

    for i, a in enumerate(rest):
        if used[i]:
            continue
        used[i] = True
        group = [a]
        grown = True
        while grown:
            grown = False
            right = max(group, key=lambda l: l["bbox"]["x"] + l["bbox"]["width"])
            left = min(group, key=lambda l: l["bbox"]["x"])
            best = None
            for j, b in enumerate(rest):
                if used[j]:
                    continue
                g = joinable(right, b)
                if g is None:
                    g = joinable(b, left)
                if g is not None and (best is None or g < best[0]):
                    best = (g, j)
            if best is not None:
                used[best[1]] = True
                group.append(rest[best[1]])
                grown = True
        if len(group) == 1:
            out.append(a)
            continue
        group.sort(key=lambda l: l["bbox"]["x"])
        x0 = min(l["bbox"]["x"] for l in group)
        y0 = min(l["bbox"]["y"] for l in group)
        x1 = max(l["bbox"]["x"] + l["bbox"]["width"] for l in group)
        y1 = max(l["bbox"]["y"] + l["bbox"]["height"] for l in group)
        n = sum(len(l["text"]) for l in group)
        tl, bl = group[0]["quad"][0], group[0]["quad"][3]
        tr, br = group[-1]["quad"][1], group[-1]["quad"][2]
        out.append({**group[0],
                    "text": " ".join(l["text"] for l in group), "raw_text": " ".join(l["raw_text"] for l in group),
                    "confidence": round(sum(l["confidence"] * len(l["text"]) for l in group) / max(1, n), 1),
                    "bbox": {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0},
                    "quad": [tl, tr, br, bl], "words": [w for l in group for w in l["words"]],
                    "fragments": len(group)})
    return out


def _words(text, raw, quad, char_boxes, chars, char_conf, score) -> list[dict]:
    """Word boxes: exact per-character boxes when the cleaned text kept the raw length, otherwise
    proportional positions along the line quad."""
    out = []
    flat_chars = [c for grp in chars for c in grp] if chars and isinstance(chars[0], list) else (chars or [])
    use_chars = char_boxes is not None and len(char_boxes) == len(raw) == len(text) and len(flat_chars) == len(raw)
    confs = [float(c) for c in (char_conf or [])] if char_conf else []
    pos = 0
    n = max(1, len(text))
    tl, tr, br, bl = quad
    for w in text.split(" "):
        if not w:
            pos += 1
            continue
        a, b = pos, pos + len(w)
        if use_chars:
            pts = np.array([p for cb in char_boxes[a:b] for p in cb], np.float32)
            x0, y0 = pts.min(axis=0)
            x1, y1 = pts.max(axis=0)
            wc = float(np.mean(confs[a:b])) if len(confs) == len(raw) else score
        else:
            f0, f1 = a / n, b / n
            p = np.array([tl + (tr - tl) * f0, tl + (tr - tl) * f1, bl + (br - bl) * f1, bl + (br - bl) * f0])
            x0, y0 = p.min(axis=0)
            x1, y1 = p.max(axis=0)
            wc = score
        out.append({"text": w, "confidence": round(wc * 100, 1),
                    "bbox": {"x": int(round(x0)), "y": int(round(y0)), "width": max(1, int(round(x1 - x0))),
                             "height": max(1, int(round(y1 - y0)))}})
        pos = b + 1
    return out
