"""
Image preprocessing for OCR.

Pipeline:
  1. EXIF orientation fix           (Pillow)
  2. Orientation correction          (Tesseract OSD, 90/180/270°)
  3. Deskew                          (projection-profile search, ±8°)
  -> "display image": every bounding box stored by SafeMetric refers to this image
  4. Resize / upscale for OCR
  5. Variants:
       clahe      grayscale + brightness (gamma) + CLAHE + median denoise
       adaptive   clahe + Gaussian blur + adaptive Gaussian threshold
       otsu       clahe + Gaussian blur + Otsu threshold (auto-inverted for dark labels)
       sharpen    clahe + unsharp mask
       inverted   inverted clahe (only for light-on-dark labels)
Different packages respond to different variants, so several are OCR'd and merged.
"""
from __future__ import annotations

import io
import logging

import cv2
import numpy as np
from PIL import Image, ImageOps

from .. import config

log = logging.getLogger("safemetric.preprocess")


class InvalidImage(ValueError):
    pass


def load_image(data: bytes) -> np.ndarray:
    """Decode bytes -> BGR array, honouring EXIF orientation. Raises InvalidImage."""
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()                          # detects truncated / corrupted files
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception as exc:
        raise InvalidImage("The file is not a valid or readable image (it may be corrupted).") from exc
    if min(img.size) < 50:
        raise InvalidImage("The image is too small to analyse.")
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def detect_orientation(bgr: np.ndarray) -> tuple[int, float]:
    """Return (rotation_degrees_clockwise_to_apply, confidence) using Tesseract OSD."""
    try:
        import pytesseract
        h, w = bgr.shape[:2]
        s = min(1.0, 1800 / max(h, w))
        gray = cv2.cvtColor(cv2.resize(bgr, (int(w * s), int(h * s))), cv2.COLOR_BGR2GRAY)
        osd = pytesseract.image_to_osd(gray, output_type=pytesseract.Output.DICT, timeout=20)
        return int(osd.get("rotate", 0)) % 360, float(osd.get("orientation_conf", 0.0))
    except Exception as exc:  # OSD fails on images with little text - that is fine
        log.debug("OSD unavailable: %s", exc)
        return 0, 0.0


_ROTATIONS = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}


def rotate_bound(bgr: np.ndarray, angle_cw: int) -> np.ndarray:
    code = _ROTATIONS.get(angle_cw)
    return cv2.rotate(bgr, code) if code is not None else bgr


def estimate_skew(bgr: np.ndarray, max_angle: float = 8.0, step: float = 0.5) -> float:
    """Projection-profile deskew: the angle whose row histogram is 'sharpest' aligns the text lines."""
    h, w = bgr.shape[:2]
    s = min(1.0, 900 / max(h, w))
    gray = cv2.cvtColor(cv2.resize(bgr, (int(w * s), int(h * s))), cv2.COLOR_BGR2GRAY)
    binv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    if (binv > 0).mean() > 0.5:
        binv = 255 - binv
    hh, ww = binv.shape
    center = (ww / 2, hh / 2)
    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-max_angle, max_angle + 1e-6, step):
        m = cv2.getRotationMatrix2D(center, angle, 1.0)
        rot = cv2.warpAffine(binv, m, (ww, hh), flags=cv2.INTER_NEAREST, borderValue=0)
        profile = rot.sum(axis=1, dtype=np.float64)
        score = float(np.var(np.diff(profile)))
        if score > best_score:
            best_score, best_angle = score, float(angle)
    return best_angle


def deskew(bgr: np.ndarray, angle: float) -> np.ndarray:
    if abs(angle) < 0.5:
        return bgr
    h, w = bgr.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    cos, sin = abs(m[0, 0]), abs(m[0, 1])
    nw, nh = int(h * sin + w * cos), int(h * cos + w * sin)
    m[0, 2] += nw / 2 - w / 2
    m[1, 2] += nh / 2 - h / 2
    return cv2.warpAffine(bgr, m, (nw, nh), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def _legacy_geometry(bgr: np.ndarray) -> tuple[np.ndarray, dict]:
    """Original method: Tesseract OSD (90/180/270) + projection-profile deskew (+/-8 degrees)."""
    steps = []
    M = np.eye(3)
    rot, conf = detect_orientation(bgr)
    if rot and conf >= 2.0:
        h, w = bgr.shape[:2]
        bgr = rotate_bound(bgr, rot)
        R = {90: np.array([[0, -1, h - 1], [1, 0, 0], [0, 0, 1]], np.float64),
             180: np.array([[-1, 0, w - 1], [0, -1, h - 1], [0, 0, 1]], np.float64),
             270: np.array([[0, 1, 0], [-1, 0, w - 1], [0, 0, 1]], np.float64)}[rot]
        M = R @ M
        steps.append(f"Orientation corrected by {rot}° (OSD confidence {conf:.1f})")
    skew = estimate_skew(bgr)
    if abs(skew) >= 0.5:
        h, w = bgr.shape[:2]
        m = cv2.getRotationMatrix2D((w / 2, h / 2), skew, 1.0)
        cos, sin = abs(m[0, 0]), abs(m[0, 1])
        nw, nh = int(h * sin + w * cos), int(h * cos + w * sin)
        m[0, 2] += nw / 2 - w / 2
        m[1, 2] += nh / 2 - h / 2
        bgr = deskew(bgr, skew)
        M = np.vstack([m, [0, 0, 1]]) @ M
        steps.append(f"Deskewed by {skew:+.1f}°")
    return bgr, {"rotation": rot if conf >= 2.0 else 0, "skew": round(skew, 2), "steps": steps,
                 "matrix": M.tolist(), "method": "tesseract_osd+projection"}


def make_display_image(bgr: np.ndarray, method: str | None = None) -> tuple[np.ndarray, dict]:
    """
    Straighten the photograph. Returns (display image, info). info["matrix"] is the 3x3 transform
    original-pixel -> display-pixel, so evidence boxes can always be mapped back to the upload.

    auto:   PP-OCR text-line geometry - any rotation angle, 0/180 decided by recognition confidence.
            Falls back to the legacy Tesseract method when PP-OCR finds too little text.
    legacy: Tesseract OSD + projection deskew (limited to +/-8 degrees).
    """
    method = (method or config.OCR_GEOMETRY)
    if method != "legacy":
        from . import ppocr
        try:
            geo = ppocr.estimate_geometry(bgr)
        except Exception as exc:  # never let geometry estimation break an inspection
            log.warning("PP-OCR geometry failed: %s", exc)
            geo = None
        if geo is not None:
            angle = geo["angle"]
            steps = []
            M = np.eye(3)
            if abs(angle) >= 0.5:
                bgr, M = ppocr.rotate_expand(bgr, angle)
                what = "turned upright (180°) and " if geo["flipped"] else ""
                steps.append(f"Text lines {what}rotated by {angle:+.1f}° (PP-OCR line geometry, "
                             f"{geo['lines']} lines, {geo['dominant_share'] * 100:.0f}% agree)")
            rot = int(round(angle / 90.0)) * 90
            return bgr, {"rotation": rot % 360, "skew": round(angle - rot, 2), "steps": steps, "matrix": M.tolist(),
                         "method": "ppocr_geometry", "geometry": geo}
    return _legacy_geometry(bgr)


def _gamma(gray: np.ndarray, gamma: float) -> np.ndarray:
    table = np.array([((i / 255.0) ** (1 / gamma)) * 255 for i in range(256)]).astype("uint8")
    return cv2.LUT(gray, table)


def build_variants(display_bgr: np.ndarray) -> tuple[dict[str, np.ndarray], float, list[str]]:
    """Build complementary OCR variants.

    Package labels are not limited to black text on white paper.  We keep the
    original colour information long enough to derive luminance/channel variants,
    then create contrast/threshold variants.  The OCR service can select the
    useful subset without changing the evidence image.
    """
    h, w = display_bgr.shape[:2]
    longest = max(h, w)
    scale = 1.0
    if longest > config.OCR_MAX_SIDE:
        scale = config.OCR_MAX_SIDE / longest
    elif longest < config.OCR_MIN_SIDE:
        scale = min(3.0, config.OCR_MIN_SIDE / longest)

    img = display_bgr if scale == 1.0 else cv2.resize(
        display_bgr, (int(w * scale), int(h * scale)),
        interpolation=cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA)

    steps = [f"Resized ×{scale:.2f} to {img.shape[1]}×{img.shape[0]}px"
             if scale != 1.0 else "Native resolution kept"]

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    lab_l = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)[..., 0]
    hsv_v = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[..., 2]
    channels = cv2.split(img)

    mean = float(gray.mean())
    if mean < 90:
        gray = _gamma(gray, 1.6)
        lab_l = _gamma(lab_l, 1.6)
        hsv_v = _gamma(hsv_v, 1.6)
        steps.append("Brightness enhancement (gamma 1.6)")
    elif mean > 200:
        gray = _gamma(gray, 0.8)
        lab_l = _gamma(lab_l, 0.8)
        hsv_v = _gamma(hsv_v, 0.8)
        steps.append("Highlight compression (gamma 0.8)")

    gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
    lab_l = cv2.normalize(lab_l, None, 0, 255, cv2.NORM_MINMAX)
    hsv_v = cv2.normalize(hsv_v, None, 0, 255, cv2.NORM_MINMAX)
    steps.append("Luminance, LAB-L and HSV-V contrast normalisation")

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    clahe = cv2.medianBlur(clahe, 3)
    lab_clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8)).apply(lab_l)
    v_clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8)).apply(hsv_v)
    steps.append("CLAHE local contrast enhancement + median noise reduction")

    blurred = cv2.GaussianBlur(clahe, (3, 3), 0)
    adaptive = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 12)
    otsu = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    dark_background = (otsu == 0).mean() > 0.55
    if dark_background:
        otsu = 255 - otsu
        adaptive = 255 - adaptive

    # Sharpen both the neutral luminance and the LAB luminance channel.
    sharp = cv2.addWeighted(clahe, 1.6, cv2.GaussianBlur(clahe, (0, 0), 2.0), -0.6, 0)
    lab_sharp = cv2.addWeighted(lab_clahe, 1.7, cv2.GaussianBlur(lab_clahe, (0, 0), 2.0), -0.7, 0)

    variants = {
        "clahe": clahe,
        "lab_l": lab_clahe,
        "hsv_v": v_clahe,
        "adaptive": adaptive,
        "otsu": otsu,
        "sharpen": sharp,
        "lab_sharpen": lab_sharp,
    }

    # Colour-channel OCR is useful for red/green/blue package text that has
    # weak grayscale contrast.  Add only the channel with the strongest
    # normalized spread to avoid tripling OCR work on every photograph.
    channel_scores = [(float(np.std(ch)), idx, ch) for idx, ch in enumerate(channels)]
    _, channel_idx, best_channel = max(channel_scores, key=lambda x: x[0])
    channel_name = ("blue", "green", "red")[channel_idx]
    variants["channel_best"] = cv2.createCLAHE(
        clipLimit=2.0, tileGridSize=(8, 8)).apply(best_channel)
    steps.append(f"Best colour channel retained for OCR ({channel_name})")

    if dark_background or mean < 110:
        variants["inverted"] = 255 - clahe
        variants["inverted_lab"] = 255 - lab_clahe
        steps.append("Inverted variants for light-on-dark text")

    return variants, scale, steps

def encode_jpeg(bgr: np.ndarray, quality: int = 90) -> bytes:
    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise InvalidImage("Could not encode processed image")
    return buf.tobytes()
