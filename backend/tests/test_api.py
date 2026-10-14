"""End-to-end API test with real OCR on the bundled sample photographs."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.ocr import tesseract_status

SAMPLES = Path(__file__).resolve().parents[2] / "samples"
needs_ocr = pytest.mark.skipif(not tesseract_status()["available"], reason="Tesseract not installed")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def headers(client):
    r = client.post("/api/auth/register", json={"name": "Test Inspector", "email": "t@example.gov.in", "password": "Passw0rd!"})
    assert r.status_code == 201, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def test_auth_required(client):
    assert client.get("/api/inspections").status_code == 401


def test_bad_login(client):
    assert client.post("/api/auth/login", json={"email": "nobody@x.in", "password": "wrongpass1"}).status_code == 401


def test_health(client):
    assert client.get("/api/health").json()["database"] == "ok"


def test_rejects_bad_upload(client, headers):
    iid = client.post("/api/inspections", json={"product_name": "X", "category": "food"}, headers=headers).json()["id"]
    r = client.post(f"/api/inspections/{iid}/images", files=[("files", ("a.txt", b"hello", "text/plain"))], headers=headers)
    assert r.status_code == 415
    r = client.post(f"/api/inspections/{iid}/images", files=[("files", ("a.jpg", b"not an image", "image/jpeg"))], headers=headers)
    assert r.status_code == 422
    assert client.post(f"/api/inspections/{iid}/analyze", headers=headers).status_code == 422   # no image


@needs_ocr
def test_full_inspection_flow(client, headers):
    r = client.post("/api/inspections", json={"product_name": "Whole Wheat Atta", "category": "food", "all_panels_captured": True},
                    headers=headers)
    iid = r.json()["id"]
    files = [("files", (f"{s}.jpg", (SAMPLES / "wheat_atta_defective" / f"{s}.jpg").read_bytes(), "image/jpeg")) for s in ("front", "back")]
    r = client.post(f"/api/inspections/{iid}/images", files=files, data={"sides": ["front", "back"]}, headers=headers)
    assert r.status_code == 201
    d = client.post(f"/api/inspections/{iid}/analyze?sync=true", headers=headers).json()
    assert d["status"] == "COMPLETED"
    assert d["overall_status"] == "NON_COMPLIANT"
    checks = {f["check_id"]: f["status"] for f in d["findings"]}
    assert checks["R12_QUALIFIER"] == "NON_COMPLIANT"
    assert checks["R11_STANDARD_UNIT"] == "NON_COMPLIANT"
    mrp = next(f for f in d["fields"] if f["field"] == "mrp")
    assert mrp["bbox"] and mrp["source_side"] == "front"
    assert d["images"][0]["ocr"]["lines"][0]["bbox"]
    for ext, magic in (("pdf", b"%PDF"), ("docx", b"PK"), ("xlsx", b"PK")):
        r = client.get(f"/api/inspections/{iid}/report.{ext}", headers=headers)
        assert r.status_code == 200 and r.content.startswith(magic)
    hist = client.get("/api/inspections?q=atta", headers=headers).json()
    assert hist["total"] >= 1
    assert client.get("/api/dashboard", headers=headers).json()["non_compliant"] >= 1
