"""
Image quality assessment performed BEFORE OCR.

Each metric is measured deterministically with OpenCV and graded GOOD / ACCEPTABLE / POOR.
The overall grade never blocks the user - it produces a warning and is used by the rule
engine to decide whether a missing declaration can be treated as conclusively absent.
"""
from __future__ import annotations

import cv2
import numpy as np

GOOD, ACCEPTABLE, POOR = "GOOD", "ACCEPTABLE", "POOR"
POOR_WARNING = "Image quality may reduce OCR accuracy. Consider uploading a clearer image."


def _grade(value: float, good: float, acceptable: float, higher_is_better: bool = True) -> str:
    if higher_is_better:
        return GOOD if value >= good else ACCEPTABLE if value >= acceptable else POOR
    return GOOD if value <= good else ACCEPTABLE if value <= acceptable else POOR


def assess_quality(bgr: np.ndarray) -> dict:
    h, w = bgr.shape[:2]
    # normalise analysis size so thresholds are resolution independent
    scale = 1400 / max(h, w)
    small = cv2.resize(bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else bgr
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)

    short_side = min(h, w)
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())
    contrast = float(gray.std())
    noise = float(np.mean(np.abs(gray.astype(np.int16) - cv2.medianBlur(gray, 3).astype(np.int16))))
    # specular glare = clipped pixels (all channels saturated); a white label background is not clipped
    glare_mask = (small.min(axis=2) >= 250) & (hsv[..., 1] <= 25)
    glare_mask = cv2.morphologyEx(glare_mask.astype(np.uint8), cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    # a white studio / paper background around the pack touches the photo border - that is not glare on the label
    n_cc, cc = cv2.connectedComponents(glare_mask)
    if n_cc > 1:
        border = np.unique(np.concatenate([cc[0], cc[-1], cc[:, 0], cc[:, -1]]))
        glare_mask[np.isin(cc, border[border > 0])] = 0
    glare = float(glare_mask.mean() * 100)
    edges = cv2.Canny(gray, 80, 200)
    edge_density = float((edges > 0).mean() * 100)

    metrics = {
        "resolution": {"value": f"{w}×{h}px", "short_side": short_side,
                       "grade": _grade(short_side, 1000, 600)},
        "blur": {"value": round(blur, 1), "unit": "Laplacian variance", "grade": _grade(blur, 120, 45)},
        "brightness": {"value": round(brightness, 1), "unit": "mean 0-255",
                       "grade": GOOD if 70 <= brightness <= 210 else ACCEPTABLE if 45 <= brightness <= 235 else POOR},
        "contrast": {"value": round(contrast, 1), "unit": "std-dev", "grade": _grade(contrast, 45, 25)},
        "noise": {"value": round(noise, 2), "unit": "mean abs residual", "grade": _grade(noise, 6, 12, higher_is_better=False)},
        "glare": {"value": round(glare, 2), "unit": "% of area", "grade": _grade(glare, 5, 15, higher_is_better=False)},
        "text_visibility": {"value": round(edge_density, 2), "unit": "% edge pixels", "grade": _grade(edge_density, 1.5, 0.6)},
    }
    grades = [m["grade"] for m in metrics.values()]
    critical_poor = any(metrics[k]["grade"] == POOR for k in ("resolution", "blur", "text_visibility"))
    if critical_poor or grades.count(POOR) >= 2:
        overall = POOR
    elif POOR in grades or grades.count(ACCEPTABLE) >= 2:
        overall = ACCEPTABLE
    else:
        overall = GOOD

    warnings = []
    labels = {"resolution": "Low resolution", "blur": "Image appears blurred", "brightness": "Poor exposure",
              "contrast": "Low contrast", "noise": "High noise", "glare": "Glare / reflections detected",
              "text_visibility": "Little visible text detected"}
    for k, m in metrics.items():
        if m["grade"] == POOR:
            warnings.append(labels[k])
    if overall == POOR:
        warnings.insert(0, POOR_WARNING)
    return {"status": overall, "metrics": metrics, "warnings": warnings}
