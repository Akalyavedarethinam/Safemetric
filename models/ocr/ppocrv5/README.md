# PP-OCRv5 (mobile) ONNX models

| file | role | sha256 |
|---|---|---|
| `det.onnx` | DB text-line **detector** (PP-OCRv5 mobile det) | `4d97c44a20d30a81aad087d6a396b08f786c4635742afc391f6621f5c6ae78ae` |
| `rec.onnx` | SVTR/CTC text-line **recogniser** (PP-OCRv5 mobile rec, multilingual dictionary embedded, includes `₹`) | `5825fc7ebf84ae7a412be049820b4d86d77620f204a041697b0494669b1742c5` |

* Origin: PaddleOCR PP-OCRv5 models (Apache-2.0), ONNX conversion as redistributed in the
  `onnxocr` 3.1.0 PyPI wheel (Apache-2.0, see `LICENSE-Apache-2.0.txt`).
* They are **pretrained**. SafeMetric does not fine-tune them (see PROJECT_REPORT.md, "Why no OCR fine-tuning").
* Run through `rapidocr_onnxruntime` (its bundled PP-OCRv4 models and 180° classifier are used as the
  fallback when this folder is missing).
* Re-download: `pip download onnxocr==3.1.0 --no-deps` and copy `onnxocr/models/ppocrv5/{det,rec}/*.onnx` here.
