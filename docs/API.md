# REST API Reference

Interactive OpenAPI documentation is available at **`/docs`** (Swagger) and **`/redoc`** when the server is running.
All endpoints except `/api/health`, `/api/auth/login` and `/api/auth/register` require the header
`Authorization: Bearer <access_token>`.

Errors always return `{"detail": "<human-readable message>"}` with the appropriate HTTP status.

## Authentication
| Method | Path | Body / notes |
|---|---|---|
| POST | `/api/auth/login` | `{email, password}` → `{access_token, token_type, expires_in, user}` |
| POST | `/api/auth/register` | `{name, email, password, designation?, jurisdiction?, phone?}` → token (role: inspector) |
| GET | `/api/auth/me` | current user |
| PUT | `/api/auth/me` | update profile |
| POST | `/api/auth/change-password` | `{current_password, new_password}` |
| POST | `/api/auth/logout` | records an audit entry (JWTs are stateless) |

## Inspections
| Method | Path | Notes |
|---|---|---|
| POST | `/api/inspections` | `{product_name, brand, category, manufacturer_info, is_imported, registration_number, inspector_name, inspection_datetime, location, notes, all_panels_captured}` |
| GET | `/api/inspections` | `q, status, category, processing, date_from, date_to, mine, sort, order, page, page_size` |
| GET | `/api/inspections/export.csv` | inspection register as CSV |
| GET | `/api/inspections/{id}` | full record: images (with OCR lines and bboxes), fields, findings, attachments, summary |
| PUT | `/api/inspections/{id}` | update product information |
| DELETE | `/api/inspections/{id}` | owner or admin |
| POST | `/api/inspections/{id}/images` | multipart: `files[]`, `sides[]`, `panel_width_mm[]`, `panel_height_mm[]` |
| GET | `/api/inspections/{id}/images` | images with quality and OCR data |
| PATCH | `/api/inspections/{id}/images/{image_id}` | `{side, panel_width_mm, panel_height_mm}` |
| DELETE | `/api/inspections/{id}/images/{image_id}` | |
| POST | `/api/inspections/{id}/analyze` | starts the analysis (202). `?sync=true` runs it inline and returns the full record. |
| GET | `/api/inspections/{id}/progress` | `{status, stage, stage_label, progress, error}` |
| GET | `/api/inspections/{id}/results` | overall status, score, fields, findings, recommendations |
| POST | `/api/inspections/{id}/attachments` | multipart `file`, `caption` (supporting evidence: jpg/png/webp/pdf) |
| DELETE | `/api/inspections/{id}/attachments/{aid}` | |
| GET | `/api/inspections/{id}/report.pdf` · `.docx` · `.xlsx` | reports |

`GET /api/inspections/{id}` also returns `summary.structured`: the normalised structured output (product name,
brand, net quantity, MRP, dates, batch, manufacturer name and address, customer care, FSSAI, origin, importer,
unit sale price), each with `value`, `confidence`, `status`, `evidence`, `bbox` and `method`
(`rules` | `line_role_model` | `layout_heuristic`). It also returns `summary.ocr_problem`, a readable warning when
no text or only low-confidence text was found. Every OCR pass in `images[].ocr.passes[]` keeps its unmodified engine
output in `text`.

## Quick label scan (no record is stored)
| Method | Path | Notes |
|---|---|---|
| POST | `/api/ocr/scan` | multipart: `file` (jpg/png/webp), `side`, `category`, `is_imported`. Returns quality, preprocessing and geometry steps, OCR text (clean + raw per pass, lines with boxes), `structured` output, all fields and **potential** findings for this one photo. With only one photo, missing declarations are always "needs verification". |

### Example result fragment
```json
{
  "overall_status": "NON_COMPLIANT", "score": 47.3, "earned_points": 26.5, "applicable_points": 56,
  "fields": [{
    "field": "mrp", "value": "₹42.00", "confidence": 96.0, "status": "DETECTED",
    "source_image": "front.jpg", "source_side": "front", "evidence": "MRP Rs. 42",
    "bbox": {"x": 150, "y": 690, "width": 330, "height": 60},
    "normalized": {"amount": 42.0, "currency": "INR", "inclusive_of_taxes": false}
  }],
  "findings": [{
    "check_id": "R6_MRP", "rule_no": "6", "title": "Retail sale price (MRP) declaration",
    "status": "NON_COMPLIANT", "severity": "HIGH",
    "reason": "Contradictory MRP declarations on the same package: ₹42.00, ₹45.00. ...",
    "evidence": [{"text": "MRP Rs. 42", "side": "front", "bbox": {...}, "confidence": 96}],
    "recommendation": "Remove the conflicting price declaration so that only one MRP appears."
  }]
}
```

## Platform
| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | database; OCR (`engine` mode, `engine_label`, PP-OCR model status, Tesseract version / languages); line-role model status; storage backend |
| GET | `/api/meta` | categories, package sides, upload limits |
| GET | `/api/dashboard` | counts, pass rate, average score, trend, top violations, recent inspections |
| GET | `/api/reports/summary` | violations by rule and by category |
| GET | `/api/rules` · `/api/rules/{rule_no}` | rule catalogue with full specifications |
| PUT | `/api/rules/{check_id}` | admin: `{active: bool}` |
| POST | `/api/registration/verify` | `{number}`: Rule 27 integration point |
| GET | `/api/files/images/{image_id}?variant=display|original` | authenticated image download |
| GET | `/api/files/attachments/{id}` | authenticated attachment download |
| GET/POST/PUT | `/api/users`, `/api/users/{id}` | admin user management |
| GET | `/api/audit` | admin: audit log |

## cURL walkthrough
```bash
TOKEN=$(curl -s -X POST localhost:8000/api/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"admin@safemetric.gov.in","password":"Admin@12345"}' | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
ID=$(curl -s -X POST localhost:8000/api/inspections -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"product_name":"Basmati Rice","category":"food"}' | python -c 'import sys,json;print(json.load(sys.stdin)["id"])')
curl -s -X POST localhost:8000/api/inspections/$ID/images -H "Authorization: Bearer $TOKEN" \
  -F files=@samples/basmati_rice_1kg/front.jpg -F sides=front -F files=@samples/basmati_rice_1kg/back.jpg -F sides=back
curl -s -X POST "localhost:8000/api/inspections/$ID/analyze?sync=true" -H "Authorization: Bearer $TOKEN" | head -c 600
curl -s localhost:8000/api/inspections/$ID/report.pdf -H "Authorization: Bearer $TOKEN" -o report.pdf
```
