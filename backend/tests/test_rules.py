"""Unit tests: text normalisation, field extraction and deterministic rules (no OCR needed)."""
from datetime import datetime

from app.rules.base import ImageInfo, RuleContext, category_config, load_config
from app.rules.registry import aggregate, run_rules
from app.services import extraction
from app.services.normalize import canonical, parse_amount, parse_date, repair_number


def _line(text, y, conf=95.0, x=50, h=30):
    words, cx = [], x
    for w in text.split(" "):
        words.append({"text": w, "confidence": conf, "bbox": {"x": cx, "y": y, "width": 14 * len(w), "height": h}})
        cx += 14 * len(w) + 10
    return {"text": text, "confidence": conf, "bbox": {"x": x, "y": y, "width": cx - x, "height": h}, "words": words}


def _extract(lines_by_side, product=""):
    imgs = []
    for i, (side, texts) in enumerate(lines_by_side.items()):
        lines = [_line(t, 100 + 45 * k) for k, t in enumerate(texts)]
        imgs.append({"image_id": i + 1, "image_name": f"{side}.jpg", "side": side, "passes": [{"lines": lines}], "merged": lines})
    return extraction.extract_fields(imgs, product), imgs


def _ctx(fields, imgs, category="food", imported=False, all_panels=True):
    infos = [ImageInfo(id=i["image_id"], name=i["image_name"], side=i["side"], quality_status="GOOD", width=1000, height=1400,
                       panel_width_mm=None, panel_height_mm=None, mean_confidence=95.0, lines=i["merged"]) for i in imgs]
    return RuleContext(category=category, is_imported=imported, registration_number="", all_panels_captured=all_panels,
                       inspection_date=datetime(2026, 9, 1), product_name="", fields=fields, images=infos,
                       category_cfg=category_config(category), common=load_config("common_rules.json"))


def by_id(findings):
    return {f["check_id"]: f for f in findings}


# ------------------------------------------------------------------ normalisation
def test_canonical_variants():
    assert "MRP" in canonical("M.R.P. Rs.120")
    assert "₹120" in canonical("M.R.P. Rs.120").replace(" ", "")
    assert "NET WEIGHT" in canonical("Net Wt. 500 g")
    assert "CONSUMER CARE" in canonical("Customer Care: 1800")


def test_repair_number_only_in_numeric_context():
    assert repair_number("1O0") == ("100", True)
    assert repair_number("5OO") == ("500", True)
    assert repair_number("OIL") == ("OIL", False)          # word, not a number: untouched
    assert parse_amount("1,250.00")[0] == 1250.0


def test_parse_date_formats():
    assert parse_date("Pkd: 08/2026")["month"] == 8
    assert parse_date("MAR 2026")["month"] == 3
    assert parse_date("12/08/2026")["year"] == 2026


# ------------------------------------------------------------------ extraction
def test_extracts_core_declarations():
    f, _ = _extract({"front": ["Net Quantity: 1 kg", "MRP ₹185.00 (Inclusive of all taxes)"],
                     "back": ["Manufactured & Packed by:", "Royal Foods Pvt Ltd,", "Nagpur, Maharashtra - 440016",
                              "Month & Year of Packing: 08/2026", "Customer Care: 1800 123 4567", "Unit Sale Price: ₹185.00 per kg"]})
    assert f["net_quantity"].normalized["base_value"] == 1000
    assert f["mrp"].normalized["amount"] == 185.0 and f["mrp"].normalized["inclusive_of_taxes"]
    assert f["manufacturer_packer"].normalized["pincode"] == "440016"
    assert f["mfg_date"].normalized["month"] == 8
    assert f["consumer_care"].normalized["phones"]
    assert f["unit_sale_price"].normalized["amount"] == 185.0


def test_rupee_glyph_misread_resolved_by_cross_check():
    # Tesseract often reads '₹185' as '7185'
    f, _ = _extract({"front": ["Net Quantity: 1 kg", "MRP Rs. 185"], "back": ["Unit Sale Price: 7185.00 per kg"]})
    assert f["unit_sale_price"].normalized["amount"] == 185.0
    assert f["unit_sale_price"].normalized["ocr_reading"] == 7185.0


# ------------------------------------------------------------------ rules
def test_compliant_label_never_claims_full_compliance_without_physical_checks():
    f, imgs = _extract({"front": ["Basmati Rice", "Net Quantity: 1 kg", "MRP ₹185.00 Inclusive of all taxes"],
                        "back": ["Manufactured by:", "Royal Foods Pvt Ltd,", "Nagpur - 440016", "Mfg Date: 08/2026",
                                 "Best Before: 12 months from packing", "Customer Care: 1800 123 4567",
                                 "Unit Sale Price: ₹185.00 per kg"]}, "Basmati Rice")
    res = run_rules(_ctx(f, imgs))
    r = by_id(res)
    assert r["R6_MRP"]["status"] == "PASS"
    assert r["R6_USP"]["status"] == "PASS"
    assert r["R7_LETTER_HEIGHT"]["status"] == "NEEDS_VERIFICATION"
    assert "physical scale" in r["R7_LETTER_HEIGHT"]["reason"]
    assert r["R27_REGISTRATION"]["status"] == "NEEDS_VERIFICATION"
    assert aggregate(res)["overall_status"] == "NEEDS_VERIFICATION"


def test_defects_are_non_compliant():
    f, imgs = _extract({"front": ["Net Wt. approx 500 gms", "MRP Rs. 42"], "back": ["MRP Rs. 45 plus local taxes"]})
    r = by_id(run_rules(_ctx(f, imgs)))
    assert r["R11_STANDARD_UNIT"]["status"] == "NON_COMPLIANT"
    assert r["R12_QUALIFIER"]["status"] == "NON_COMPLIANT"
    assert r["R6_MRP"]["status"] == "NON_COMPLIANT"          # two different MRPs
    assert r["S18_MISLEADING"]["status"] == "NON_COMPLIANT"
    assert aggregate(list(r.values()))["overall_status"] == "NON_COMPLIANT"


def test_missing_declaration_is_a_potential_finding_not_a_verdict():
    f, imgs = _extract({"front": ["Net Quantity: 1 kg", "MRP ₹185.00"]})
    assert by_id(run_rules(_ctx(f, imgs, all_panels=False)))["R6_CONSUMER_CARE"]["status"] == "NEEDS_VERIFICATION"
    # v2.2 default: OCR absence is never conclusive, even when the inspector confirms all panels were photographed
    r = by_id(run_rules(_ctx(f, imgs, all_panels=True)))["R6_CONSUMER_CARE"]
    assert r["status"] == "NEEDS_VERIFICATION" and "Potential finding" in r["reason"]


def test_absence_can_be_made_conclusive_by_configuration():
    f, imgs = _extract({"front": ["Net Quantity: 1 kg", "MRP ₹185.00"]})
    ctx = _ctx(f, imgs, all_panels=True)
    ctx.common = {**ctx.common, "missing_declaration": {**ctx.common["missing_declaration"],
                                                       "allow_non_compliant_from_ocr_absence": True}}
    assert by_id(run_rules(ctx))["R6_CONSUMER_CARE"]["status"] == "NON_COMPLIANT"


def test_wrong_unit_sale_price():
    f, imgs = _extract({"front": ["Net Volume: 500 ml", "MRP ₹899.00"], "back": ["Unit Sale Price: ₹2.50 per ml"]})
    assert by_id(run_rules(_ctx(f, imgs)))["R6_USP"]["status"] == "NON_COMPLIANT"


def test_category_applicability():
    f, imgs = _extract({"front": ["Net Quantity: 1 N", "MRP ₹799.00"]})
    r = by_id(run_rules(_ctx(f, imgs, category="electronics")))
    assert r["R6_USP"]["status"] == "NOT_APPLICABLE"
    assert r["R6_BEST_BEFORE"]["status"] == "NOT_APPLICABLE"
    assert r["R13_BASIS"]["status"] == "PASS"
    assert "R15_BIS" in r


def test_imported_requires_importer_and_origin():
    f, imgs = _extract({"front": ["Net Quantity: 500 ml", "MRP ₹899.00"]})
    r = by_id(run_rules(_ctx(f, imgs, imported=True, all_panels=False)))
    assert r["R6_IMPORTER"]["status"] == "NEEDS_VERIFICATION"
    assert r["R6_ORIGIN"]["status"] == "NEEDS_VERIFICATION"


def test_rule7_with_calibration():
    f, imgs = _extract({"front": ["Net Quantity: 1 kg"]})
    ctx = _ctx(f, imgs)
    ctx.images[0].panel_width_mm = 200.0     # 1000 px -> 0.2 mm/px ; numerals 30 px -> 6 mm
    r = by_id(run_rules(ctx))["R7_LETTER_HEIGHT"]
    assert r["status"] == "PASS" and "6.00 mm" in r["reason"]


def test_wrong_unit_sale_price_per_gram_is_detected():
    # ₹60 for 500 g = ₹0.12 per g; a declared ₹0.15 per g is wrong (v2.1 accepted it: fixed ₹0.50 tolerance)
    f, imgs = _extract({"front": ["Net Wt. 500 g", "MRP ₹60.00"], "back": ["Unit Sale Price: ₹0.15 per g"]})
    assert by_id(run_rules(_ctx(f, imgs)))["R6_USP"]["status"] == "NON_COMPLIANT"
    f, imgs = _extract({"front": ["Net Wt. 500 g", "MRP ₹60.00"], "back": ["Unit Sale Price: ₹0.12 per g"]})
    assert by_id(run_rules(_ctx(f, imgs)))["R6_USP"]["status"] == "PASS"
