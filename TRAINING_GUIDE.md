# SafeMetric - dataset, training and evaluation guide

Every command below runs from the project root (`safemetric/`) and was executed to produce the numbers in
`PROJECT_REPORT.md`. It needs Python 3.10+ and 2+ CPU cores. No GPU is needed.

```bash
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt                           # app + tests + dataset/eval tools
# optional but recommended: the Tesseract executable (fallback engine + legacy baseline)
#   Ubuntu: sudo apt install tesseract-ocr tesseract-ocr-eng tesseract-ocr-osd
```

## 1. What is trained, and what is not (and why)

| Module | Approach | Trained here? |
|---|---|---|
| 1. Text detection | PP-OCRv5 DB detector (pretrained, ONNX) + a line re-assembly step | No. The pretrained model measured 0.95+ detection F1 on the synthetic test set; fine-tuning a detector without a GPU is not justified for a student project (see §7). |
| 2. Text recognition | PP-OCRv5 SVTR recogniser (pretrained, ONNX) + context-safe clean-up; Tesseract 5 as fallback / comparison | No, for the same reason. The clean-up rules were tuned on the **val** split only. |
| 3a. Field extraction | Deterministic label rules (MRP, net quantity, dates, batch, FSSAI, manufacturer …) | Rule-based: labelled declarations are extracted more reliably and more explainably by rules. |
| 3b. Brand / product name | **Line-role classifier** (char n-gram TF-IDF + 21 layout features → logistic regression) | **Yes**: `training/train_line_roles.py`, compared with a layout heuristic on val. |
| 4. Compliance | Existing deterministic rule engine (Rules 6-27, S.18) | No. It is evaluated against injected defects. |

## 2. Generate and validate the datasets

```bash
python scripts/generate_datasets.py                         # default: 12,000 records, 2,400 images, seed 20260924
python scripts/validate_datasets.py                         # writes datasets/validation_report.json, exit 1 on failure
python scripts/visualize_annotations.py --split test --n 12 --words   # draws GT boxes -> datasets/_preview/
```

Useful options:

```bash
python scripts/generate_datasets.py --records 50000 --images 10000 --workers 8     # a bigger dataset
python scripts/generate_datasets.py --seed 7 --out /tmp/ds_seed7                   # an independent draw
python scripts/generate_datasets.py --records 500 --images 60 --out /tmp/smoke     # 10-second smoke test
```

* Output is byte-identical for a given seed, whatever the number of workers, when the library versions in
  `requirements-lock.txt` are used. With other OpenCV / Pillow versions the annotations are identical and pixels
  differ only slightly.
* The split is decided by brand, so growing `--records` keeps train, val and test brand-disjoint.
* Generator code: `training/datagen/`. `lexicon.py` holds the vocabulary, `records.py` the label text, fields and
  defects, `render.py` the layout, fonts, degradations and annotation transforms, and `noise.py` the OCR-noise model
  for the text-only dataset. Fonts are bundled in `training/fonts/` (open licences, see `training/fonts/LICENSES.md`).

## 3. Evaluate OCR (Modules 1 + 2)

```bash
# the configuration the application uses (PP-OCRv5 + geometry + enhancement + clean-up)
python evaluation/evaluate_ocr.py --engine ppocr --split test --tag ppocr_auto
# the ORIGINAL v2.1 OCR stage, for comparison (Tesseract multi-pass, OSD + +/-8 degree deskew, no clean-up)
python evaluation/evaluate_ocr.py --engine tesseract --geometry legacy --no-clean --split test --tag tesseract_original
# PP-OCR + 3 Tesseract passes merged
python evaluation/evaluate_ocr.py --engine hybrid --split test --tag hybrid_auto
```

Each run writes `evaluation/results/ocr_<tag>_<split>.json` (overall, per capture condition, CER per field) and
`evaluation/results/predictions/ocr_<tag>_<split>.jsonl`. The predictions file holds every predicted line (clean and
raw text, boxes in upload coordinates, all passes) and is the input for the next two steps. `--limit N` evaluates only
the first N images. On 2 CPU cores expect about 3-4 s per image for `ppocr` and 8-10 s for the Tesseract modes.

Metrics: line detection P/R/F1 (DetEval-style one-to-one match; IoU≥0.5 also reported), CER and WER per GT line
(Latin-script lines; bilingual lines reported separately), order-free bag-of-words recall and precision, and numeric
recall (prices, dates, PIN / phone / licence numbers read exactly).

## 4. Train the line-role model (Module 3b)

It needs OCR predictions for the **val** split (model selection) and, optionally, for part of **train**
(training on real OCR output as well as ground-truth lines):

```bash
python evaluation/evaluate_ocr.py --engine ppocr --split val   --tag ppocr_auto
python evaluation/evaluate_ocr.py --engine ppocr --split train --tag ppocr_auto --limit 400
python training/train_line_roles.py --ocr-tag ppocr_auto
```

The script compares two data mixes (GT lines with synthetic OCR noise, and the same plus real OCR lines) across
several regularisation strengths. It picks the best by brand / product-name selection accuracy on **val** OCR output,
chooses probability thresholds, and saves:

* `models/extraction/line_role_model.npz` + `.json`: the **portable export** the application loads
  (`LINE_ROLE_MODEL`). It is plain numpy arrays (vocabulary, IDF, scaler, weights), so the app needs neither
  scikit-learn nor pandas and cannot hit pickle / version mismatches. The script checks that it reproduces the
  scikit-learn probabilities (max difference measured: 2e-15).
* `models/extraction/line_role_model.joblib`: the original scikit-learn pipeline, kept for analysis and retraining
* `models/extraction/line_role_model_card.json`: the grid, chosen settings, thresholds and limitations

If the model files are missing, the application falls back to the layout heuristic (largest suitable text line).

## 5. Evaluate extraction (Module 3) and compliance (Module 4)

```bash
# extractor alone, ground-truth text with synthetic OCR noise (clean / light / medium / heavy)
python evaluation/evaluate_extraction.py --mode text --split test --roles model
# end to end: real OCR output of the test photos -> extraction
python evaluation/evaluate_extraction.py --mode ocr --ocr-tag ppocr_auto --split test --roles model
python evaluation/evaluate_extraction.py --mode ocr --ocr-tag ppocr_auto --split test --roles heuristic    # no ML
python evaluation/evaluate_extraction.py --mode ocr --ocr-tag tesseract_original --split test --roles heuristic
# compliance: are the injected defects raised as potential findings? false NON_COMPLIANT on clean labels?
python evaluation/evaluate_compliance.py --ocr-tag ppocr_auto --split test
# one table with every result
python evaluation/summarize_results.py            # -> evaluation/results/SUMMARY.md
```

Field scoring rules (`evaluation/metrics.py`):
* Names, importer and country: exact after lower-casing and removing punctuation.
* Address: token F1 ≥ 0.8.
* Quantity: same value and unit.
* MRP and unit sale price: numeric match.
* Dates: same canonical `MM/YYYY` or `DD/MM/YYYY`.
* Batch: alphanumerics.
* FSSAI: digits.
* Customer care: at least one phone or e-mail correct.

A wrong value counts as both a false positive and a false negative.

## 6. Tests

```bash
cd backend && pytest -q                 # 43 tests: API end-to-end with real OCR, rules, extraction, OCR upgrade
python scripts/e2e_smoke.py             # against a RUNNING server (uvicorn app.main:app --port 8000)
python scripts/analyze_label.py samples/basmati_rice_1kg/back.jpg    # one photo -> structured JSON
```

## 7. Adding more data in the future

1. **More synthetic data or new variations:**
   * vocabulary: `training/datagen/lexicon.py` (products per category, brand words, cities, statements)
   * label wording and new declarations: `records.py`
   * layouts, fonts and degradations: `render.py`

   Bump `GENERATOR_VERSION`, regenerate, validate, then re-run §3-§5.
2. **Real photographs** (strongly recommended before trusting the numbers on real packaging):
   * Put images in `datasets/real/<split>/` and write `datasets/real/ocr_annotations/<split>.jsonl` in the same schema
     as the synthetic annotations. Every line needs `text`, `quad` (4 points), `fields`, `visible`, `partial` and
     `legible`, and every image needs `expected_fields`. Any polygon tool that exports points can be used (for
     example Label Studio or PPOCRLabel, whose format matches `ppocr_det_*.txt`).
   * Split by **product / brand**, not by photo. Several photos of one pack must stay in the same split.
   * Point the evaluators at it: `--data datasets/real`.
   * Label only data you are allowed to use. Do not publish photos of real products with claims about their compliance.
3. **Fine-tuning OCR (optional, GPU recommended):** `ppocr_det_*.txt` is already in PaddleOCR's detection-label format.
   For recognition, crop the line quads (`scripts/export_rec_crops.py`) and follow PaddleOCR's fine-tuning docs.
   Export to ONNX (`paddle2onnx`), drop `det.onnx` / `rec.onnx` into `models/ocr/<name>/` and set `PPOCR_MODEL_DIR`.
   Accept the new model only if `evaluate_ocr.py` improves on the **val** split, then report on **test** once.
4. **New categories or rules:** add `backend/app/rules/config/<category>_rules.json`. The generator reads
   `unit_sale_price_applicable` from the same files, so its ground-truth defects stay consistent with the rules.
