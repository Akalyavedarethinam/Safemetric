# SafeMetric: Legal Metrology label detection, OCR and compliance checking (v2.2)

SafeMetric checks packaged-commodity labels against the **Legal Metrology Act, 2009** and the **Legal Metrology
(Packaged Commodities) Rules, 2011**. An inspector uploads photographs of the package sides, and the system:

1. checks image quality,
2. straightens the photo (any rotation angle; upside-down and 90° photos too),
3. **detects the text lines and reads them with PP-OCRv5.** It adds a second pass for dark or blurred photos,
   uses Tesseract as the fallback, and keeps the raw output of every engine,
4. cleans the OCR text with context-safe fixes (O→0 inside numbers, restored spaces),
5. extracts the declarations and a **structured product record** (product name, brand, net quantity, MRP, dates,
   batch, manufacturer, customer care, FSSAI, origin, importer, unit sale price) with confidence and evidence boxes,
6. evaluates the statutory rules with a **deterministic rule engine** and reports **potential findings**,
7. saves the inspection, shows the evidence, and generates PDF / Word / Excel reports.

> No AI model makes the compliance decision. The OCR models only read text, and the small trained model only
> suggests which line is the brand or product name. Every finding comes from an explicit, configurable rule and is
> linked to the OCR text and location that produced it. Anything a photograph cannot prove (letter height without a
> scale, spacing, registration, and since v2.2 the *absence* of a declaration) is reported as **Needs Verification**.

**New in v2.2:** see [PROJECT_REPORT.md](PROJECT_REPORT.md) for the problems found, the changes made and the
measured results, and [TRAINING_GUIDE.md](TRAINING_GUIDE.md) for the datasets, training and evaluation.

---

## Download: the project is split into 6 ZIP parts (each under 30 MB)

Extract **all parts into the same folder**. They merge into one `LegalMetrologyProject/` tree.

| Part | Contents | Needed for |
|---|---|---|
| 1 `code_docs_models` | backend, frontend (source + prebuilt UI), training / evaluation / scripts, docs, samples, fonts, trained line-role model (`.npz`), evaluation results (JSON + SUMMARY.md), dataset README / manifest | everything |
| 2 `ppocr_models` | `models/ocr/ppocrv5/det.onnx`, `rec.onnx` (PP-OCRv5) | running the app with the measured engine (without it, the older PP-OCRv4 bundled in rapidocr is used) |
| 3 `dataset_annotations` | all JSONL: `synthetic_text/`, `ocr_annotations/`, `field_extraction/` | training / evaluation |
| 4 `test_images` | the 380 test photos | OCR evaluation |
| 5 `val_and_sample_train_images` | the 312 val photos + the first 120 train photos | model selection / examples |
| 6 `ocr_predictions_and_sklearn_model` | saved OCR outputs (`evaluation/results/predictions/`) + scikit-learn pipeline (`.joblib`) | re-running extraction / compliance evaluation without re-running OCR, re-training |

The remaining train photos are not shipped. `python scripts/generate_datasets.py` regenerates all 2,400 photos
(byte-identical with `requirements-lock.txt`).

## Features

| Area | What is implemented |
|---|---|
| Intake | Product details, category (12 categories), imported flag. You can upload 1–12 images and assign each to a side (front/back/left/right/top/bottom/additional). Accepts JPG/PNG/WEBP. Optional physical calibration in mm. |
| Image quality | Checks resolution, blur (Laplacian), brightness, contrast, noise, glare and text visibility, and grades the image GOOD / ACCEPTABLE / POOR with warnings. It never blocks the upload. |
| Geometry | Text-line directions from the PP-OCR detector straighten the photo at **any angle**. The 0° vs 180° decision uses recognition confidence. Tesseract OSD + deskew is the fallback. A transform matrix maps every evidence box back to the upload. |
| OCR | **PP-OCRv5** (PaddleOCR models, run offline on CPU through ONNX Runtime). DB text-line detection + SVTR recognition, with word fragments re-joined into lines. Extra passes run on a contrast-enhanced copy (dark / low-contrast photos) and on a 2× sharpened copy (blurred photos). `OCR_ENGINE=hybrid` / `tesseract` selects the Tesseract multi-pass pipeline. |
| Clean-up | Context-safe corrections: O/o→0 and l/I→1 only inside numbers (`6O0001`→`600001`), I/l in all-caps words, dropped spaces (`BatchNo:SM2608A`→`Batch No: SM2608A`). E-mail addresses are protected. **Raw text is kept** per line and per pass. |
| Extraction | Label rules for MRP, net quantity, mfg / packing / expiry / best-before dates, batch, FSSAI, manufacturer / packer / importer with address, consumer care, origin, unit sale price, BIS, registration and more. Table-style label/value cells are paired. **Brand and product name** come from a trained line-role model (layout heuristic as fallback). Output is a flat **structured JSON**. |
| Rule engine | Rules 6, 7, 8, 9, 11/12, 13, 15 and 27 and Section 18, as separate modules plus a registry. Category-specific configuration is in JSON. Produces an overall status and a transparent weighted score. Absence of a declaration is a potential finding (Needs Verification), never proven by OCR alone. |
| Evidence | A bounding-box overlay on the straightened image. Click a declaration, structured field or finding to see where it was read. Raw OCR text is shown per pass. |
| Quick scan | `POST /api/ocr/scan` or `python scripts/analyze_label.py photo.jpg`: one photo → OCR text + structured fields + potential findings, without creating a record. |
| Records, reports, dashboard, history, security | SQLite / PostgreSQL. PDF / DOCX / XLSX / CSV. Dashboard. Search. bcrypt + JWT, roles, audit log, upload validation. *(Unchanged from v2.1.)* |
| Datasets & training | Seeded synthetic dataset generator (text, images with word/line quads, OCR ground truth, field extraction), validation, OCR / extraction / compliance evaluation scripts and a line-role training script. See TRAINING_GUIDE.md. |

## Quick start

### Option A: Docker (recommended; PP-OCR models and Tesseract are included)

```bash
docker compose up --build
# open http://localhost:8001   ·   admin@safemetric.gov.in / Admin@12345  (change it!)
```

### Option B: Local development

Prerequisites: Python 3.10+ and Node 18+ (only needed to rebuild the UI). Tesseract is optional but recommended
as the fallback engine:

* Ubuntu/Debian: `sudo apt install tesseract-ocr tesseract-ocr-eng tesseract-ocr-osd`
* macOS: `brew install tesseract`
* Windows: install from <https://github.com/UB-Mannheim/tesseract/wiki>, then
  `set TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe`

```bash
# backend  (http://127.0.0.1:8000, API docs at /docs). The prebuilt UI in frontend/dist is served too.
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt                        # includes rapidocr_onnxruntime (PP-OCR runtime)
cp .env.example .env                                   # optional
uvicorn app.main:app --reload --port 8000

# frontend dev server (optional; http://localhost:5173, proxies /api to :8000)
cd ../frontend && npm install && npm run dev
```

`models/ocr/ppocrv5/` (PP-OCRv5 ONNX models, 21 MB) and `models/extraction/line_role_model.npz` are loaded
automatically. Check `http://127.0.0.1:8000/api/health`: `ocr.engine_label` should read `PP-OCRv5` and
`line_role_model.available` should be `true`.

### Try it

```bash
python scripts/analyze_label.py samples/basmati_rice_1kg/back.jpg          # structured JSON for one photo
python scripts/seed_demo.py                                                # loads samples/ into a running server
python scripts/e2e_smoke.py                                                # API end-to-end smoke test
```

| `samples/` folder | What it demonstrates |
|---|---|
| `malt_drink_500g` | **Best demo.** Fictional malt health-drink carton, 3 product photos (front, back, left side) with every declaration: all 14 declared fields are detected. Regenerate with `python scripts/make_demo_malt_drink.py`; overview picture: `samples/malt_drink_500g_overview.jpg` |
| `basmati_rice_5kg`, `sunflower_oil_1l`, `herbal_shampoo_340ml`, `detergent_powder_1kg` | More fictional demo products (food, cosmetic, household), each photographed front / back / left: every printed declaration is detected. `python scripts/make_demo_products.py` |
| `cookies_200g_defective` | Fictional pack with deliberate defects ('approx.', 'gms', '+ local taxes extra', no expiry, no consumer care, no unit sale price). Result: **Non-Compliant** |
| `basmati_rice_1kg` | Well-labelled food product. Result: **Needs Verification**, because only physical checks remain |
| `wheat_atta_defective` | "approx", "gms", two different MRPs, "plus local taxes", missing declarations. Result: **Non-Compliant** |
| `olive_oil_imported` | Imported product with a wrong unit sale price |
| `herbal_shampoo_cosmetic`, `usb_charger_electronics` | Cosmetic and electronics category rules |
| `real_world/` | v2.1 benchmark fixtures (clean renders using real brand names; not official package photos) |
| `datasets/product_label_images/test/` | 380 synthetic, degraded label photos with ground truth (see datasets/README.md) |

### Scanning packages with the camera

In **New Inspection → Step 2** choose **Scan with camera** (or **Upload files**; both can be combined):

* **Laptop / desktop** (http://127.0.0.1:8000 or http://localhost:8000): a live camera view opens with a framing guide.
  Pick the side (Front, Back, Left …), press the shutter, check the photo and choose **Use photo** or **Retake**. The
  next side is selected automatically. Each shot gets an on-device check for blur, darkness and glare, so a bad photo
  can be retaken before upload. Multiple cameras (switch button) and the phone torch are supported where available.
* **Phone on the same Wi-Fi**: start the server with `uvicorn app.main:app --host 0.0.0.0 --port 8000` and open
  `http://<computer-IP>:8000` on the phone. Browsers only allow the live camera view on https or localhost, so on
  plain http the button opens the phone's own camera app instead; the photo is added in the same way.
* Camera photos are ordinary JPEG uploads (marked "Camera" in the list) and go through the same OCR and rule
  pipeline as uploaded files. Supporting-evidence attachments on an inspection also have a **Photo** button.

### Tests

```bash
cd backend && pip install -r requirements-dev.txt && pytest -q      # 43 tests incl. real OCR end-to-end
```

## Measured results (synthetic test split, 380 photos never used for tuning)

See PROJECT_REPORT.md §6 for the full tables, per-condition breakdown and limitations.
*The results are measured on synthetic labels and are not a guarantee for real packaging.*

| | v2.1 as uploaded | **v2.2** |
|---|---|---|
| Text-line detection F1 | 42.5 % | **95.4 %** |
| Character error rate (Latin lines) | 29.8 % | **14.6 %** |
| Numbers read exactly (prices, dates, licence / phone numbers) | 61.4 % | **75.3 %** |
| Structured fields, end-to-end micro-F1 (16 fields) | 49.6 % | **80.2 %** |
| Product name / brand F1 | no such fields | **96.4 % / 99.0 %** |
| Injected labelling defects raised as potential findings | n/a | **98.7 %** |
| Clean, fully photographed labels wrongly marked Non-Compliant | 23.7 % (v2.1 absence policy, v2.2 OCR) | **1.3 %** |
| Seconds per photo (2 CPU cores, indicative) | 11.3 | **5.2** |

Clear photos reach 2.4 % CER; blurred photos are still hard, at 34.5 % CER.

## Project layout

```
safemetric/
├── backend/app/
│   ├── services/   quality, preprocess (geometry), ppocr (NEW), ocr (engines), textclean (NEW), extraction,
│   │               line_roles (NEW), structured (NEW), label_scan (NEW), normalize, pipeline, registration
│   ├── rules/      rule6 … rule27, section18, registry, config/*.json
│   ├── routers/    auth, inspections, misc (health …), ocr (NEW: /api/ocr/scan)
│   └── reports/    pdf, docx, xlsx
├── backend/tests/  pytest suite (API end-to-end with real OCR, rules, extraction, OCR upgrade)
├── frontend/       React 18 + Vite + TypeScript (src/, prebuilt dist/)
├── models/
│   ├── ocr/ppocrv5/           det.onnx, rec.onnx (pretrained PP-OCRv5, Apache-2.0)
│   └── extraction/            line_role_model.npz/.json (trained here), .joblib, model card
├── datasets/       synthetic_text/, product_label_images/, ocr_annotations/, field_extraction/, manifest, README
├── training/       datagen/ (generator), fonts/ (bundled, open licences), train_line_roles.py
├── evaluation/     evaluate_ocr.py, evaluate_extraction.py, evaluate_compliance.py, metrics.py,
│                   summarize_results.py, results/ (JSON + SUMMARY.md)
├── scripts/        generate_datasets, validate_datasets, visualize_annotations, export_rec_crops,
│                   analyze_label, e2e_smoke, seed_demo, make_samples, benchmark_extraction, run_dev
├── docs/           ARCHITECTURE, API, DEPLOYMENT, RULES, USER_GUIDE, OCR_EXTRACTION_UPGRADE
├── requirements.txt (everything) · requirements-lock.txt (exact versions used) · README.md · TRAINING_GUIDE.md · PROJECT_REPORT.md
└── Dockerfile · docker-compose.yml · render.yaml
```

## Important limitations

* **OCR is not 100 % accurate.** Blurred, low-resolution, dark or glare-covered photos and dot-matrix stamps cause
  most errors (see the per-condition table). Low-confidence values are flagged, the raw OCR is kept, and the UI
  asks for verification.
* **The metrics come from synthetic data.** The generator is realistic but not a substitute for annotated real
  photographs. Add some (TRAINING_GUIDE.md §7) before relying on the numbers.
* **Absence of a declaration** is reported as *Needs Verification*: OCR misses must not become violations.
  Administrators can restore the v2.1 behaviour in `rules/config/common_rules.json`, but this is not recommended.
* **Physical checks:** Rule 7 letter height needs panel dimensions, and Rule 27 registration needs an authoritative
  registry.
* **Rule tables:** verify the Rule 7 tables and category configuration against the currently notified text before
  using the system for enforcement.
* **Hindi / regional text:** it is not recognised well by the Latin-script models (reported separately). Tesseract
  can use `OCR_LANG=eng+hin` if the `hin` model is installed.
* **Fictional names:** synthetic samples use fictional brands. The v2.1 `samples/real_world` fixtures use real
  brand names only as OCR test renders and are not package photographs.
