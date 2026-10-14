# SafeMetric — Software Architecture

## 1. Overview

```
 Browser (React SPA)                         FastAPI application (Python)
 ┌─────────────────────┐   HTTPS / JSON     ┌──────────────────────────────────────────────┐
 │ Landing · Login      │ ─────────────────► │ routers/auth.py         JWT + bcrypt         │
 │ Dashboard            │   Bearer JWT       │ routers/inspections.py  CRUD, upload, analyze│
 │ New Inspection wizard│                    │ routers/misc.py         dashboard, rules,    │
 │ Inspection details   │ ◄───────────────── │                         users, files, health │
 │ History · Reports    │   progress polling │                                              │
 │ Rules · Users        │                    │ services/pipeline.py  (background thread)    │
 └─────────────────────┘                    │   quality → preprocess → OCR → extraction    │
                                            │   → rules/registry → persist                 │
                                            │ reports/  PDF · DOCX · XLSX                  │
                                            └───────┬───────────────────────┬──────────────┘
                                                    │ SQLAlchemy            │ storage.py
                                            ┌───────▼────────┐     ┌────────▼───────────────┐
                                            │ SQLite / Postgres│   │ Local FS / S3 / R2 /    │
                                            │ (metadata, OCR,  │   │ Supabase / GCS / Azure  │
                                            │ fields, findings)│   │ (image binaries)        │
                                            └──────────────────┘   └────────────────────────┘
                              PP-OCRv5 ONNX models (models/ocr) · Tesseract OCR executable (TESSERACT_CMD, fallback)
```

In production, a single container serves the built SPA (`frontend/dist`) and the API from the same origin.

## 2. Processing pipeline (`services/pipeline.py`)

| # | Stage | Module | Output |
|---|---|---|---|
| 1 | Load & validate | `preprocess.load_image` | BGR array (EXIF-corrected). Corrupt files are rejected. |
| 2 | Quality check | `quality.assess_quality` | 7 metrics, GOOD/ACCEPTABLE/POOR and warnings |
| 3 | Orientation & deskew | `preprocess.make_display_image` → `ppocr.estimate_geometry` | the **display image**: rotated by ANY angle from the PP-OCR text-line directions, 0/180° chosen by recognition confidence; falls back to Tesseract OSD + projection deskew. `matrix` maps upload → display pixels |
| 4 | Variants | `preprocess.build_variants` | CLAHE / adaptive / Otsu / sharpened / inverted variants (used by the Tesseract passes only) |
| 5 | OCR | `ocr.run_ocr` → `ppocr.ocr_lines` | PP-OCRv5 DB text-line detection + SVTR recognition on the colour image; word fragments re-joined into lines; extra pass on a contrast-enhanced copy for dark / low-contrast photos. `OCR_ENGINE=hybrid/tesseract` adds or uses the Tesseract passes |
| 6 | Clean-up + merge | `textclean.clean_text`, `ocr.merge_passes` | context-safe fixes (O→0 inside numbers, restored spaces, MAGGl→MAGGI); `raw_text` kept per line and per pass |
| 7 | Extraction | `extraction.extract_fields` + `line_roles` + `structured` | label rules produce candidates from every pass, clustered by location, best selected, conflicting values kept as alternatives; table key/value cells joined; brand / product name from the trained line-role model (heuristic fallback); flat `structured` output |
| 8 | Price cross-check | `extraction.resolve_price_ambiguity` | settles ₹-glyph misreads only when the MRP, quantity and unit sale price corroborate each other |
| 9 | Rules | `rules/registry.run_rules` | one finding per check, then `aggregate` gives the overall status and score |
| 10 | Persist | pipeline | OcrResult, ExtractedField and RuleFinding rows, summary, recommendations, SHA-256 integrity hash |

Analysis runs in a background thread. The UI polls `GET /api/inspections/{id}/progress`, which reports the
stage and percentage. `?sync=true` runs the analysis inline, for scripts and tests. Analyses left unfinished by a restart are marked
FAILED at start-up so they can be re-run.

## 3. Rule engine (`app/rules/`)

* `base.py` defines `CheckSpec` (rule number, title, reference, severity, applicability, required data, condition,
  verification requirement) and `CheckResult` (status, reason, evidence, recommendation). It also defines `RuleContext`, which
  carries the extracted fields, the image information, the category configuration and the settings.
* There is one module per rule: `rule6.py`, `rule7.py`, `rule8.py`, `rule9.py`, `rule11_12.py`, `rule13.py`, `rule15.py`,
  `rule27.py` and `section18.py`. Each rule is a `Rule` subclass with a list of checks and an `evaluate(ctx)` method.
* `registry.py` holds the list of rules, the catalogue for the UI, administrator deactivation, the aggregation and the recommendations.
* `config/*.json` holds all thresholds, severity weights, units, the Rule 7 tables and the per-category configuration.
  **To add a category, add `config/<key>_rules.json`.** It then appears automatically in the UI.

Overall status:
1. any HIGH-severity NON_COMPLIANT check → **NON_COMPLIANT**
2. any other NON_COMPLIANT check → **PARTIALLY_COMPLIANT**
3. otherwise, any NEEDS_VERIFICATION check → **NEEDS_VERIFICATION**
4. otherwise → **COMPLIANT**

Score = Σ(weight × credit) / Σ(applicable weight). Weights: HIGH 3, MEDIUM 2, LOW 1. Credit: Pass 1, Needs Verification 0.5, Non-Compliant 0.
The score is informational only; the status rules above decide the verdict.

## 4. Data model

```
users 1─* inspections 1─* inspection_images 1─1 ocr_results
                      1─* extracted_fields
                      1─* rule_findings
                      1─* evidence_attachments
rule_settings (check_id → active)      audit_logs (user, action, detail, ip, time)
```
All tables have timestamps. Images are stored under server-generated UUID keys. The database holds only the keys,
the SHA-256 hash and the metadata. JSON columns hold OCR lines (with bboxes), parsed values, evidence and the summary.

## 5. Security

* Passwords are hashed with bcrypt (12 rounds). The password policy requires at least 8 characters with a letter and a digit.
* JWT (HS256) sessions are signed with `SECRET_KEY`, with a configurable expiry. In production the app refuses to start with the development key.
* Roles: `admin` manages users, activates rules and reads the audit log. `inspector` creates and analyses inspections.
  Only the owner or an admin can modify or delete a record. All authenticated users can read the repository.
* Failed logins are throttled per email and IP (8 per 15 minutes). An audit log records login, register, create, upload, analyze,
  report, user and rule changes.
* Uploads are checked against an extension whitelist and a size limit, and must decode as real images (Pillow `verify`). PDFs are checked for the `%PDF` header.
  Storage keys are never derived from user filenames.
* Image files are served only through authenticated endpoints. The SPA fetches them as blobs with the bearer token.
* Security headers are set (nosniff, frame deny, referrer policy). CORS is restricted to the origins in `ALLOWED_ORIGINS`.
* Global exception handlers return friendly messages, and stack traces go only to the server log.

## 6. Frontend

React 18 + TypeScript + Vite and React Router, with a hand-written CSS design system (`src/styles.css`) and lucide icons.
Reusable components: `Layout` (sidebar and top bar with engine status), `ui.tsx` (badges, stat cards, score ring,
modal, toasts, authorised image loader), and `EvidenceViewer` (percentage-positioned bbox overlays that stay aligned at any size).
The layout is responsive down to 360 px, with an off-canvas sidebar on mobile.

## 7. Extensibility

* **New rule:** subclass `Rule` in a new module and add it to `RULES` in `registry.py`.
* **New category:** add a JSON file in `rules/config/`.
* **New storage backend:** implement `put/get/delete` in `storage.py`.
* **Official registration API:** set `REGISTRATION_API_URL`, or adapt `services/registration.py`.
* **Additional OCR languages:** install the `tesseract-ocr-<lang>` packages and set `OCR_LANG=eng+hin`.
