"""Tests for the v2.2 OCR / extraction upgrade: text clean-up, bug fixes, new fields, structured output,
PP-OCR geometry and engine fallback."""
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.services import extraction, structured
from app.services.textclean import clean_text

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


def _line(text, y, conf=95.0, h=30):
    words, x = [], 50
    for w in text.split(" "):
        words.append({"text": w, "confidence": conf, "bbox": {"x": x, "y": y, "width": 14 * len(w), "height": h}})
        x += 14 * len(w) + 10
    return {"text": text, "confidence": conf, "bbox": {"x": 50, "y": y, "width": x - 50, "height": h}, "words": words}


def _fields(texts, heights=None, roles="heuristic"):
    heights = heights or [30] * len(texts)
    lines, y = [], 40
    for t, h in zip(texts, heights):
        lines.append(_line(t, y, h=h))
        y += int(h * 1.5)
    return extraction.extract_fields([{"image_id": 1, "image_name": "t.jpg", "side": "front",
                                       "passes": [{"lines": lines}], "merged": lines}], "", roles=roles)


# ------------------------------------------------------------------ text clean-up
@pytest.mark.parametrize("raw,clean", [
    ("BatchNo:SM26O8A", "Batch No: SM2608A"),
    ("Plot 21, Chennai - 6OOOO1", "Plot 21, Chennai - 600001"),
    ("Month&Year ofPacking:O8/2026", "Month & Year of Packing: 08/2026"),
    ("Unit Sale Price: Rs.199.O0 perkg", "Unit Sale Price: Rs. 199.00 per kg"),
    ("Manufactured by: MAGGl Foods", "Manufactured by: MAGGI Foods"),
    ("Email: customercare@brand.example.in", "Email: customercare@brand.example.in"),   # e-mail untouched
    ("SOS OIL", "SOS OIL"),                                                               # words untouched
    ("Net Vol. 5l", "Net Vol. 5l"),                                                       # 5 litres, not 51
])
def test_clean_text(raw, clean):
    assert clean_text(raw) == clean


# ------------------------------------------------------------------ regressions fixed in v2.2
def test_batch_no_is_not_read_as_nos():
    f = _fields(["Batch No: SM2608A", "FSSAI Lic. No. 11521999000123"])
    assert f["batch_number"].value == "SM2608A"
    assert f["fssai_license"].value == "11521999000123"


def test_batch_code_starting_with_rs_is_not_a_price():
    assert _fields(["B. No. RS1125A"])["batch_number"].value == "RS1125A"


def test_unit_price_label_and_unparsable_usp():
    assert _fields(["Unit Price: Rs.85.00 per kg"])["unit_sale_price"].normalized["amount"] == 85.0
    f = _fields(["Unit Sale Price: see pack"])
    assert f["unit_sale_price"].normalized.get("unparsed")


def test_contents_label_for_count_quantities():
    q = _fields(["Contents: 10 U"])["net_quantity"]
    assert q.normalized["base_value"] == 10 and q.normalized["dimension"] == "number"


# ------------------------------------------------------------------ new fields + structured output
def test_structured_output_matches_the_requirement_example():
    f = _fields(["SUNRISE", "SUNRISE RICE", "NET WT: 5 kg", "MRP: ₹650.00", "PACKED ON: 09/2026",
                 "BEST BEFORE: 6 MONTHS", "BATCH NO: SR0926A"], heights=[70, 50, 30, 30, 22, 22, 22])
    out = structured.structured_output(f)
    assert out["net_quantity"] == "5 kg"
    assert out["mrp"] == "650.00"
    assert out["packed_on"] == "09/2026"
    assert out["best_before"] == "6 months"
    assert out["batch_number"] == "SR0926A"
    assert out["product_name"] == "SUNRISE RICE"
    assert "mfg_date" not in out and "expiry_date" not in out


def test_dates_are_separated_by_label():
    out = structured.structured_output(_fields(["Mfg. Date: 04/2026", "PKD: 05/2026", "EXP: 03/2027"]))
    assert (out["mfg_date"], out["packed_on"], out["expiry_date"]) == ("04/2026", "05/2026", "03/2027")


def test_manufacturer_name_and_address_are_split():
    out = structured.structured_output(_fields(["Manufactured by: Silver Leaf Agro Foods Pvt. Ltd.",
                                                "Plot No. 21, MIDC Industrial Area,", "Nagpur, Maharashtra - 440016"]))
    assert out["manufacturer_name"] == "Silver Leaf Agro Foods Pvt. Ltd."
    assert out["manufacturer_address"].endswith("440016")


def test_marketer_is_not_reported_as_manufacturer():
    out = structured.structured_output(_fields(["Marketed by: Prime Consumer Goods Ltd.", "Sector 63, Noida - 201301"]))
    assert "manufacturer_name" not in out


# ------------------------------------------------------------------ PP-OCR engine
ppocr = pytest.importorskip("app.services.ppocr")
needs_pp = pytest.mark.skipif(not ppocr.available(), reason="rapidocr_onnxruntime not installed")


@needs_pp
@pytest.mark.parametrize("angle", [12, -20, 90, 180])
def test_geometry_straightens_rotated_labels(angle):
    img = cv2.imread(str(SAMPLES / "real_world" / "maggi" / "back.jpg"))
    rot, _ = ppocr.rotate_expand(img, -angle)                 # rotate clockwise by `angle`
    geo = ppocr.estimate_geometry(rot)
    assert geo is not None
    residual = ((geo["angle"] - angle) + 180) % 360 - 180
    assert abs(residual) < 2.5, geo


@needs_pp
def test_ppocr_reads_rotated_label_that_defeated_tesseract():
    from app.services import ocr, preprocess
    img = cv2.imread(str(SAMPLES / "real_world" / "maggi" / "back.jpg"))
    rot, _ = ppocr.rotate_expand(img, -12)
    display, info = preprocess.make_display_image(rot)
    variants, scale, _ = preprocess.build_variants(display)
    res = ocr.run_ocr(variants, scale, display, "ppocr")
    f = extraction.extract_fields([{"image_id": 1, "image_name": "r.jpg", "side": "back", "passes": res["passes"],
                                    "merged": res["lines"]}])
    assert f["batch_number"].value == "SM2608A"
    assert f["fssai_license"].value == "11521999000123"
    assert np.allclose(np.asarray(info["matrix"]).shape, (3, 3))


# ------------------------------------------------------------------ trained line-role model
def test_line_role_model_finds_brand_and_product():
    from app.services import line_roles
    if line_roles.load_model() is None:
        pytest.skip("line-role model not trained")
    f = _fields(["SILVER LOTUS", "100% Natural", "Premium Basmati Rice", "Net Wt. 5 kg", "MRP ₹650.00",
                 "Batch No: SR0926A"], heights=[64, 22, 44, 30, 26, 20], roles="model")
    assert f["brand_name"].value == "SILVER LOTUS"
    assert f["product_name"].value == "Premium Basmati Rice"
    assert f["brand_name"].normalized["method"] == "line_role_model"
