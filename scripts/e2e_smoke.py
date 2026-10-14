"""
End-to-end smoke test against a RUNNING SafeMetric server (API + OCR + extraction + rules + reports).

    uvicorn app.main:app --port 8000          (in backend/)
    python scripts/e2e_smoke.py --base http://127.0.0.1:8000

Cases: well-labelled sample, defective sample, a rotated + blurred synthetic photo, a synthetic label with a
missing declaration, an image with no text at all, and a file that is not an image. Prints one line per case and
exits non-zero if an API call fails unexpectedly.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
from pathlib import Path

import httpx
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def blank_jpeg() -> bytes:
    rng = np.random.default_rng(0)
    arr = (rng.normal(128, 6, (600, 800, 3))).clip(0, 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, "JPEG")
    return buf.getvalue()


def pick_synthetic(cond: str, defect: str | None = None) -> Path | None:
    p = ROOT / "datasets" / "ocr_annotations" / "test.jsonl"
    if not p.exists():
        return None
    for line in open(p, encoding="utf-8"):
        r = json.loads(line)
        if (not cond or cond in r["conditions"]) and (defect is None or defect in r["defects"]) and (ROOT / "datasets" / r["image"]).exists():
            return ROOT / "datasets" / r["image"]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--email", default="e2e.inspector@example.gov.in")
    ap.add_argument("--password", default="E2eTest#2026")
    a = ap.parse_args()
    c = httpx.Client(base_url=a.base, timeout=600)
    r = c.post("/api/auth/register", json={"name": "E2E Inspector", "email": a.email, "password": a.password})
    if r.status_code not in (201, 409, 400):
        sys.exit(f"register failed: {r.status_code} {r.text}")
    r = c.post("/api/auth/login", json={"email": a.email, "password": a.password})
    r.raise_for_status()
    c.headers["Authorization"] = "Bearer " + r.json()["access_token"]
    print("health:", c.get("/api/health").json()["ocr"].get("engine_label"))

    cases = [
        ("well-labelled (samples/basmati_rice_1kg)", "food", True,
         [("front", ROOT / "samples/basmati_rice_1kg/front.jpg"), ("back", ROOT / "samples/basmati_rice_1kg/back.jpg")]),
        ("defective (samples/wheat_atta_defective)", "food", True,
         [("front", ROOT / "samples/wheat_atta_defective/front.jpg"), ("back", ROOT / "samples/wheat_atta_defective/back.jpg")]),
        ("synthetic rotated photo", "food", False, [("front", pick_synthetic("rotated"))]),
        ("synthetic blurry photo", "food", False, [("front", pick_synthetic("blurry"))]),
        ("synthetic label with a missing MRP", "food", False, [("front", pick_synthetic("", "missing:mrp"))]),
        ("photo without any text", "food", False, [("front", "BLANK")]),
    ]
    failures = 0
    for name, cat, all_panels, files in cases:
        files = [(s, p) for s, p in files if p]
        if not files:
            print(f"- {name}: skipped (dataset not generated)")
            continue
        iid = c.post("/api/inspections", json={"product_name": "", "category": cat, "all_panels_captured": all_panels}).json()["id"]
        up = [("files", (f"{s}.jpg", blank_jpeg() if p == "BLANK" else Path(p).read_bytes(), "image/jpeg")) for s, p in files]
        r = c.post(f"/api/inspections/{iid}/images", files=up, data={"sides": [s for s, _ in files]})
        if r.status_code != 201:
            print(f"- {name}: upload failed {r.status_code} {r.text[:200]}")
            failures += 1
            continue
        t = time.time()
        d = c.post(f"/api/inspections/{iid}/analyze?sync=true").json()
        st = d.get("summary", {}).get("structured", {})
        found = {k: v["value"] for k, v in st.items() if v.get("found")}
        nc = [f["check_id"] for f in d.get("findings", []) if f["status"] == "NON_COMPLIANT"]
        print(f"- {name}: {d['status']} {d.get('overall_status')} in {time.time() - t:.1f}s  "
              f"ocr_problem={bool(d.get('summary', {}).get('ocr_problem'))}\n    structured={found}\n    non_compliant={nc}")
        if d["status"] != "COMPLETED":
            failures += 1
        for ext, magic in (("pdf", b"%PDF"), ("docx", b"PK"), ("xlsx", b"PK")):
            rr = c.get(f"/api/inspections/{iid}/report.{ext}")
            if rr.status_code != 200 or not rr.content.startswith(magic):
                print(f"    report.{ext} FAILED {rr.status_code}")
                failures += 1
    # quick single-image scan endpoint + invalid upload
    r = c.post("/api/ocr/scan", files={"file": ("x.jpg", (ROOT / "samples/olive_oil_imported/back.jpg").read_bytes(), "image/jpeg")},
               data={"category": "food"})
    print("- /api/ocr/scan:", r.status_code, r.json().get("structured") if r.status_code == 200 else r.text[:200])
    failures += r.status_code != 200
    r = c.post("/api/ocr/scan", files={"file": ("x.jpg", b"not an image", "image/jpeg")})
    print("- invalid image ->", r.status_code, r.json().get("detail"))
    failures += r.status_code != 422
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
