# Statutory Rule Specifications

Generated from the rule engine catalogue (`GET /api/rules`). Each check is deterministic and returns
**PASS**, **NON_COMPLIANT**, **NEEDS_VERIFICATION** or **NOT_APPLICABLE**, together with a reason and the OCR evidence it used.

> Verify the thresholds and tables in `backend/app/rules/config/` against the currently notified statutory text before enforcement use.

## Overall status

1. `Any NON_COMPLIANT check with HIGH severity  -> NON_COMPLIANT`
2. `Any other NON_COMPLIANT check              -> PARTIALLY_COMPLIANT`
3. `Else any NEEDS_VERIFICATION check           -> NEEDS_VERIFICATION`
4. `Else                                        -> COMPLIANT`

**Score:** score = Σ(weight × credit) / Σ(weight of applicable checks) × 100. NOT_APPLICABLE checks are excluded from the denominator. The score is informational; the overall status is decided by the status rules below. Severity weights: HIGH=3, MEDIUM=2, LOW=1.

**Missing declarations:** A declaration that is simply not found is NEEDS_VERIFICATION. It is treated as conclusively missing (NON_COMPLIANT) only when the inspector confirms that every label panel was photographed AND no image is POOR quality AND mean OCR confidence is at least this value.


## Rule 6 — Declarations to be made on every package

### `R6_MANUFACTURER` · Name and complete address of manufacturer / packer  (HIGH)

* **Reference:** Legal Metrology (Packaged Commodities) Rules, 2011 - Rule 6(1)
* **Applicability:** All retail packages
* **Required data:** manufacturer_packer
* **Validation condition:** A 'manufactured/packed by' declaration with a name and a complete address (PIN code) is present.

### `R6_IMPORTER` · Name and complete address of importer  (HIGH)

* **Reference:** Legal Metrology (Packaged Commodities) Rules, 2011 - Rule 6(1)
* **Applicability:** Imported packages (inspector marked product as imported)
* **Required data:** importer
* **Validation condition:** An 'imported by' declaration with the importer's name and complete address is present.

### `R6_COMMON_NAME` · Common or generic name of the commodity  (MEDIUM)

* **Reference:** Legal Metrology (Packaged Commodities) Rules, 2011 - Rule 6(1)
* **Applicability:** All retail packages
* **Required data:** generic_name
* **Validation condition:** The common/generic name of the commodity is declared.

### `R6_NET_QUANTITY` · Net quantity declaration  (HIGH)

* **Reference:** Legal Metrology (Packaged Commodities) Rules, 2011 - Rule 6(1)
* **Applicability:** All retail packages
* **Required data:** net_quantity
* **Validation condition:** A net quantity with a numeric value and a unit is declared (format checked under Rules 11/12).

### `R6_MRP` · Retail sale price (MRP) declaration  (HIGH)

* **Reference:** Legal Metrology (Packaged Commodities) Rules, 2011 - Rule 6(1)
* **Applicability:** All retail packages
* **Required data:** mrp
* **Validation condition:** A single, unambiguous MRP amount in Indian Rupees is declared.

### `R6_MRP_TAXES` · MRP declared inclusive of all taxes  (MEDIUM)

* **Reference:** Legal Metrology (Packaged Commodities) Rules, 2011 - Rule 6(1)
* **Applicability:** All retail packages
* **Required data:** mrp
* **Validation condition:** The MRP declaration states it is inclusive of all taxes.

### `R6_DATE` · Month and year of manufacture / packing / import  (HIGH)

* **Reference:** Legal Metrology (Packaged Commodities) Rules, 2011 - Rule 6(1)
* **Applicability:** All retail packages
* **Required data:** mfg_date
* **Validation condition:** A month and year of manufacture, packing or import is declared and is not later than the inspection date.

### `R6_BEST_BEFORE` · Best before / use by date  (MEDIUM)

* **Reference:** Legal Metrology (Packaged Commodities) Rules, 2011 - Rule 6(1)
* **Applicability:** Commodities that may become unfit for consumption (category configuration: best_before_required)
* **Required data:** best_before, mfg_date
* **Validation condition:** A best-before / use-by / expiry declaration is present and is not earlier than the manufacture date.

### `R6_CONSUMER_CARE` · Consumer care details  (HIGH)

* **Reference:** Legal Metrology (Packaged Commodities) Rules, 2011 - Rule 6(1)
* **Applicability:** All retail packages
* **Required data:** consumer_care
* **Validation condition:** Consumer-care contact details (telephone number and/or e-mail) are declared.

### `R6_ORIGIN` · Country of origin / manufacture  (MEDIUM)

* **Reference:** Legal Metrology (Packaged Commodities) Rules, 2011 - Rule 6(1)
* **Applicability:** Imported packages
* **Required data:** country_of_origin
* **Validation condition:** The country of origin or manufacture/assembly is declared.

### `R6_USP` · Unit sale price  (MEDIUM)

* **Reference:** Legal Metrology (Packaged Commodities) Rules, 2011 - Rule 6(1)
* **Applicability:** Packages sold by weight or volume (category configuration: unit_sale_price_applicable)
* **Required data:** unit_sale_price, mrp, net_quantity
* **Validation condition:** A unit sale price is declared and equals MRP ÷ net quantity (per declared unit) within tolerance.


## Rule 7 — Principal display panel - size of letters and numerals

### `R7_LETTER_HEIGHT` · Minimum height of numerals in the net quantity declaration  (HIGH)

* **Reference:** Legal Metrology (Packaged Commodities) Rules, 2011 - Rule 7
* **Applicability:** All retail packages
* **Required data:** net_quantity, image calibration (panel width/height in mm)
* **Validation condition:** Measured numeral height (pixels × mm-per-pixel from inspector calibration) ≥ minimum in the configured Rule 7 table. Without a physical calibration the check cannot be decided.
* **Verification requirement:** Measure the height of the net-quantity numerals with a scale/vernier on the physical package.


## Rule 8 — Principal display panel - placement and spacing

### `R8_PDP_IMAGE` · Principal display panel photographed  (LOW)

* **Reference:** Legal Metrology (Packaged Commodities) Rules, 2011 - Rule 8
* **Applicability:** All retail packages
* **Required data:** image side designation
* **Validation condition:** At least one uploaded image is designated as the FRONT (principal display panel).
* **Verification requirement:** Photograph the panel most likely to be displayed to the consumer and mark it as Front.

### `R8_NET_QTY_ON_PDP` · Net quantity shown on the principal display panel  (HIGH)

* **Reference:** Legal Metrology (Packaged Commodities) Rules, 2011 - Rule 8
* **Applicability:** All retail packages
* **Required data:** net_quantity, image side designation
* **Validation condition:** The net quantity declaration is located on an image designated FRONT.
* **Verification requirement:** Confirm on the physical package that the net quantity is on the principal display panel.

### `R8_SPACING` · Spacing, grouping and physical placement of declarations  (MEDIUM)

* **Reference:** Legal Metrology (Packaged Commodities) Rules, 2011 - Rule 8
* **Applicability:** All retail packages
* **Required data:** physical package
* **Validation condition:** Spacing/clear-space and physical placement requirements cannot be reliably measured from photographs.
* **Verification requirement:** Inspect the physical package for spacing and placement requirements.


## Rule 9 — Legibility and prominence of declarations

### `R9_LEGIBILITY` · Legibility of mandatory declarations  (HIGH)

* **Reference:** Legal Metrology (Packaged Commodities) Rules, 2011 - Rule 9
* **Applicability:** All retail packages
* **Required data:** net_quantity, mrp, mfg_date, manufacturer_packer, consumer_care
* **Validation condition:** Every extracted key declaration has OCR confidence ≥ threshold and text/background contrast ratio ≥ threshold (configured in common_rules.json) on a non-POOR image. NON_COMPLIANT only if contrast is below the configured hard minimum on a GOOD quality image.
* **Verification requirement:** Visually confirm legibility under normal lighting.

### `R9_PROMINENCE` · Prominence of the net quantity declaration  (MEDIUM)

* **Reference:** Legal Metrology (Packaged Commodities) Rules, 2011 - Rule 9
* **Applicability:** All retail packages
* **Required data:** net_quantity
* **Validation condition:** Net-quantity numeral height ≥ median text height on the same panel.
* **Verification requirement:** Visually confirm that the net quantity is conspicuous.


## Rule 11/12 — Quantity declaration - value and units

### `R11_VALUE_UNIT` · Numeric value with a unit  (HIGH)

* **Reference:** Legal Metrology (Packaged Commodities) Rules, 2011 - Rules 11 & 12
* **Applicability:** All retail packages
* **Required data:** net_quantity
* **Validation condition:** The net quantity has a positive numeric value followed by a recognised unit.

### `R11_STANDARD_UNIT` · Standard unit symbols  (MEDIUM)

* **Reference:** Legal Metrology (Packaged Commodities) Rules, 2011 - Rules 11 & 12
* **Applicability:** All retail packages
* **Required data:** net_quantity
* **Validation condition:** The unit is one of the standard symbols/names configured in units.json (e.g. g, kg, mL, L, cm, m, N, pieces). Non-standard spellings such as 'gms', 'kgs', 'ltrs' are non-compliant.

### `R12_QUALIFIER` · No non-standard qualifying expressions  (HIGH)

* **Reference:** Legal Metrology (Packaged Commodities) Rules, 2011 - Rules 11 & 12
* **Applicability:** All retail packages
* **Required data:** net_quantity
* **Validation condition:** The quantity declaration is not qualified by expressions such as 'approx.', 'about', 'minimum', 'when packed' (list configured in units.json).


## Rule 13 — Declaration of quantity by weight, measure or number

### `R13_BASIS` · Quantity basis appropriate to the commodity  (MEDIUM)

* **Reference:** Legal Metrology (Packaged Commodities) Rules, 2011 - Rule 13
* **Applicability:** Categories with a configured quantity basis (see <category>_rules.json)
* **Required data:** net_quantity, category
* **Validation condition:** The dimension of the declared unit (mass / volume / length / area / number) is one of the bases configured for the selected category. Anything else - or a category without configuration - needs verification.
* **Verification requirement:** Confirm the commodity-specific manner of declaration.


## Rule 15 — Specific commodity / package declarations

### `R15_SPECIFIC` · Category-specific additional declarations  (MEDIUM)

* **Reference:** Legal Metrology (Packaged Commodities) Rules, 2011 - Rule 15 (commodity-specific declarations)
* **Applicability:** Only for categories whose configuration lists additional declarations
* **Required data:** category configuration
* **Validation condition:** Each configured additional declaration for the selected category is detected on the package. A missing declaration is NEEDS_VERIFICATION (these requirements often come from other statutes).
* **Verification requirement:** Verify commodity-specific declarations against the applicable regulation.

### `R15_FSSAI_LICENCE` · FSSAI licence number  (MEDIUM)

* **Reference:** Food Safety and Standards (Labelling and Display) Regulations, 2020
* **Applicability:** Categories: Beverage, Food
* **Required data:** fssai_license
* **Validation condition:** 'FSSAI licence number' is detected on the package.
* **Verification requirement:** Verify commodity-specific declarations against the applicable regulation.

### `R15_INGREDIENTS` · List of ingredients  (LOW)

* **Reference:** Commodity-specific labelling regulation
* **Applicability:** Categories: Beverage, Cosmetic, Food
* **Required data:** ingredients
* **Validation condition:** 'List of ingredients' is detected on the package.
* **Verification requirement:** Verify commodity-specific declarations against the applicable regulation.

### `R15_NUTRITION` · Nutritional information  (LOW)

* **Reference:** Food Safety and Standards (Labelling and Display) Regulations, 2020
* **Applicability:** Categories: Beverage, Food
* **Required data:** nutrition_info
* **Validation condition:** 'Nutritional information' is detected on the package.
* **Verification requirement:** Verify commodity-specific declarations against the applicable regulation.

### `R15_BATCH` · Batch / lot number  (LOW)

* **Reference:** Commodity-specific labelling regulation
* **Applicability:** Categories: Cosmetic, Personal care, Pharmaceutical / non-pharmaceutical packaged goods
* **Required data:** batch_number
* **Validation condition:** 'Batch / lot number' is detected on the package.
* **Verification requirement:** Verify commodity-specific declarations against the applicable regulation.

### `R15_BIS` · BIS registration / standard mark (R-number or IS mark)  (MEDIUM)

* **Reference:** BIS Compulsory Registration Order (where the product is notified)
* **Applicability:** Categories: Electrical goods, Electronics
* **Required data:** bis_mark
* **Validation condition:** 'BIS registration / standard mark (R-number or IS mark)' is detected on the package.
* **Verification requirement:** Verify commodity-specific declarations against the applicable regulation.

### `R15_SIZE` · Size / dimensions declaration  (LOW)

* **Reference:** Commodity-specific declaration (Rule 15 type)
* **Applicability:** Categories: Clothing / textile
* **Required data:** size_dimensions
* **Validation condition:** 'Size / dimensions declaration' is detected on the package.
* **Verification requirement:** Verify commodity-specific declarations against the applicable regulation.


## Rule 27 — Registration of manufacturers, packers and importers

### `R27_REGISTRATION` · Registration of the manufacturer / packer / importer  (MEDIUM)

* **Reference:** Legal Metrology (Packaged Commodities) Rules, 2011 - Rule 27
* **Applicability:** Manufacturers, packers and importers of pre-packaged commodities
* **Required data:** registration_number (inspector input or label), authoritative registry
* **Validation condition:** The registration number is confirmed as valid by an authoritative registration source.
* **Verification requirement:** Verify registration with the Legal Metrology registration records.


## Section 18 — Misleading / non-standard declarations

### `S18_MISLEADING` · Configured misleading price expressions  (HIGH)

* **Reference:** Legal Metrology Act, 2009 - Section 18 read with PCR 2011
* **Applicability:** All retail packages
* **Required data:** full OCR text
* **Validation condition:** None of the misleading expressions configured in common_rules.json (e.g. 'plus taxes', 'taxes extra') appear in the OCR text. PASS requires mean OCR confidence ≥ the configured minimum; otherwise the absence cannot be relied upon.
* **Verification requirement:** Review the package for other misleading representations (strike-throughs, stickers over MRP etc.).

## Category configuration

| Category | Quantity basis | Best before | Unit sale price | Additional declarations |
|---|---|---|---|---|
| Food | mass, volume, number | required | applicable | FSSAI licence number; List of ingredients; Nutritional information |
| Beverage | volume, mass | required | applicable | FSSAI licence number; List of ingredients; Nutritional information |
| Cosmetic | mass, volume, number | required | applicable | Batch / lot number; List of ingredients |
| Personal care | mass, volume, number | required | applicable | Batch / lot number |
| Household goods | mass, volume, number, length | — | applicable | — |
| Electronics | number | — | — | BIS registration / standard mark (R-number or IS mark) |
| Electrical goods | number, length | — | — | BIS registration / standard mark (R-number or IS mark) |
| Clothing / textile | number, length, area | — | — | Size / dimensions declaration |
| Hardware | number, mass, length | — | — | — |
| Stationery | number, length, mass | — | — | — |
| Pharmaceutical / non-pharmaceutical packaged goods | number, mass, volume | required | — | Batch / lot number |
| Other | — (verify) | — | applicable | — |

## Units (Rules 11/12)

* Accepted standard units/symbols: L, N, U, cm, cm², g, kg, m, mL, mg, mm, m², pair, pieces (plus their full names)
* Recognised but non-standard (flagged): cc, gm, gms, grm, grms, kgs, kilo, lt, ltr, ltrs, lts, mls, mtr, mtrs
* Qualifying expressions flagged: approx, approximately, about, around, more or less, minimum, min., not less than, nearly, ±, +/-, when packed, w/o packing

## Rule 7 tables (minimum numeral height, normal print)

| PDP area (cm²) up to | mm |
|---|---|
| 100 | 1 |
| 500 | 2 |
| 2500 | 4 |
| above | 6 |

| Net quantity (g or mL) up to | mm |
|---|---|
| 50 | 1 |
| 200 | 2 |
| 1000 | 4 |
| above | 6 |

Measurement tolerance: 15%. Without an inspector-supplied calibration the result is NEEDS_VERIFICATION: *Requires reliable physical scale/reference for letter/numeral height.*
