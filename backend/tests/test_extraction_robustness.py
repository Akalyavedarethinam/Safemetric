"""Regression tests for OCR-tolerant declaration extraction."""
from app.services import extraction


def _line(text, y=100, conf=92.0):
    words = []
    x = 50
    for w in text.split():
        words.append({
            "text": w, "confidence": conf,
            "bbox": {"x": x, "y": y, "width": max(12, 14 * len(w)), "height": 32},
        })
        x += max(12, 14 * len(w)) + 10
    return {"text": text, "confidence": conf,
            "bbox": {"x": 50, "y": y, "width": max(100, x - 50), "height": 32},
            "words": words}


def _extract(texts):
    lines = [_line(t, 100 + i * 50) for i, t in enumerate(texts)]
    return extraction.extract_fields([{
        "image_id": 1, "image_name": "font-test.jpg", "side": "front",
        "passes": [{"lines": lines}], "merged": lines
    }], "Tata Salt")


def test_spaced_ocr_labels_and_units():
    f = _extract([
        "N E T W T : 1 K G",
        "M R P Rs 185",
        "C U S T O M E R C A R E 1800 123 4567",
    ])
    assert f["net_quantity"].normalized["base_value"] == 1000
    assert f["mrp"].normalized["amount"] == 185
    assert f["consumer_care"].normalized["phones"]


def test_common_ocr_numeric_confusions():
    f = _extract(["Net Wt. 5OO G", "M.R.P. Rs. 1O5"])
    assert f["net_quantity"].normalized["base_value"] == 500
    assert f["mrp"].normalized["amount"] == 105
