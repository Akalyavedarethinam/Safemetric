> **v2.2 update:** the default OCR engine is now PP-OCRv5 (text-line detection and recognition), with any-angle
> straightening, contrast and blur passes, a context-safe clean-up, a trained brand / product-name model and a
> structured output. The Tesseract pipeline described below is still available (`OCR_ENGINE=tesseract` or `hybrid`)
> and is the automatic fallback. See `PROJECT_REPORT.md` for the measured comparison and `TRAINING_GUIDE.md` for
> the datasets.

# SafeMetric OCR & Extraction Upgrade

## What changed

### 1. OCR preprocessing
- Added LAB-L and HSV-V luminance variants.
- Added best colour-channel OCR.
- Added LAB sharpening.
- Kept adaptive, Otsu, CLAHE, sharpening and inverted variants.
- Increased default OCR working size for mobile/package photographs.

### 2. Tesseract coverage
- Added more segmentation/layout combinations.
- Added a 300 DPI hint.
- OCR line ranking now gives a small semantic bonus to declaration lines such as MRP, net quantity, dates, FSSAI and consumer care.

### 3. Extraction tolerance
- Matching-only OCR cleanup handles spaced labels:
  - `N E T W T` -> `NET WT`
  - `M R P` -> `MRP`
  - `F S S A I` -> `FSSAI`
  - `C U S T O M E R C A R E` -> `CUSTOMER CARE`
- Handles spaced units such as `K G`, `M L`, `G M`.
- Added manufacturing-date matching for common OCR wording.
- Original OCR remains stored as evidence.

### 4. Sample coverage
Added synthetic OCR benchmark fixtures using common real-world product/brand names across:
food, beverages, personal care, household, electronics, electrical, textile, stationery and hardware.

### 5. Regression tests
Added tests for spaced OCR labels and numeric OCR confusions.

## Important

This improves robustness; it does not make OCR perfect for every font or photograph. Decorative fonts, severe blur, glare, tiny ink-jet dates, curved text and occlusion can still require human verification.

For a future second OCR engine, use the same OCR service interface and compare engines before accepting a value. Do not let a new model silently override evidence or rule-engine safeguards.
