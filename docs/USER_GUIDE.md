# User Guide — Inspecting Officers

## Signing in
Open the application and choose **Officer Sign In**. New officers can use **Create Account** (Inspector role) unless
self-registration has been disabled. The first administrator is `admin@safemetric.gov.in` / `Admin@12345`. Change this
password under **Settings & Profile** immediately.

## Running an inspection
1. **New Inspection → Product details.** Enter the product name, brand and **category** (the category decides which rules
   apply). Tick **Imported product** if applicable, which enables the importer and country-of-origin checks. The registration number is optional (Rule 27).
2. **Upload images.** Add one photograph per panel that carries text (up to 12; JPG, PNG or WEBP, max 10 MB each). Set each
   image's side. Mark the **principal display panel as Front**.
   * Tips: fill the frame, avoid glare, hold the camera parallel to the label, and use good light.
   * *Physical calibration (optional).* If a photo is cropped exactly to one panel, enter that panel's width and height in mm.
     Rule 7 can then measure the numeral height in millimetres.
   * Tick **"I confirm every label panel has been photographed"** only if you really captured all sides. Only then can a
     declaration that is not found be reported as *Non-Compliant* instead of *Needs Verification*.
3. **Analyze.** The progress panel shows each stage: uploading, image check, processing, OCR, extraction, rules, saving.
   A typical photo takes 3–15 seconds.
4. **Results.**
   * **Compliance Result:** the overall status, the score (with its full calculation under *View formula & breakdown*) and the
     actions required.
   * **Declarations:** each extracted value with its confidence and source. Click a row to see it on the photo.
   * **Rule Findings:** each check with its reason, condition, applicability and evidence. Use *Show on image* to see the location.
   * **Images & Evidence:** the photos with highlighted declarations, the quality metrics, the preprocessing steps and the raw OCR text.
   * **Record & Attachments:** attach further evidence (seizure memo, shelf photo, PDF), correct image sides or calibration, then
     **Re-analyze**.
5. **Reports.** Download the PDF (for signature), or the Word/Excel versions if you need to edit them.

## Reading the statuses
| Status | Meaning |
|---|---|
| Pass | The configured condition is satisfied by the evidence. |
| Non-Compliant | A configured condition is clearly violated. The evidence shows what and where. |
| Needs Verification | The photos cannot decide this check. Examine the physical package. **This is not a pass.** |
| Not Applicable | The check does not apply to this category or product, or was deactivated by an administrator. |

Overall **Needs Verification** means no violation was established, but some checks (for example letter height, spacing or
registration) still require physical or authoritative verification.

## History, dashboard and reports
* **Inspection History:** search by reference, product, brand, manufacturer, inspector or location. Filter by status, category or date,
  sort by any column, and export CSV.
* **Dashboard:** status counts, pass rate, 14-day trend, most frequent violations and recent activity.
* **Reports:** violations by rule and category, plus downloads for every completed inspection.

## Administrators
* **User Management:** add officers, change roles, deactivate accounts and reset passwords.
* **Statutory Rules:** view every check's specification and activate or deactivate checks.
* **Settings:** engine status and the audit log.

## v2.2: structured product information and OCR debugging

* **Declarations → Structured product information:** the normalised values read from the label (product name,
  brand, net quantity, MRP, manufacturing / packing / expiry / best-before dates, batch, manufacturer name and
  address, customer care, FSSAI, country of origin, importer, unit sale price), with confidence and how each was
  found:
  * *label rules*: a printed declaration label such as "MRP" or "Batch No."
  * *layout model / heuristic*: brand and product name, recognised from print size and position. Always verify these.

  Click a row to see the text on the photo. **Copy JSON** copies the structured output.
* **Images & Evidence → OCR text:** *Merged (cleaned)* is the text used for extraction. *PP-OCR raw* and the
  Tesseract passes show the unmodified engine output, kept for debugging.
* **Photograph / OCR problem** banner: shown when no readable text or only low-confidence text was found. The
  inspection still completes, but every declaration becomes "needs verification". Retake the photo in even light,
  fill the frame with the label, avoid glare and hold the camera steady.
* **Quick scan without saving:** `POST /api/ocr/scan`, or `python scripts/analyze_label.py photo.jpg`.
