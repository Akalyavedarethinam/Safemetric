"""
Load the sample package photographs into a running SafeMetric server through the public API.

    python scripts/seed_demo.py [--url http://127.0.0.1:8000] [--email admin@safemetric.gov.in] [--password Admin@12345]
"""
import argparse
import json
import mimetypes
import urllib.request
import uuid
from pathlib import Path

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
PRODUCTS = [
    ("basmati_rice_1kg", "Premium Basmati Rice", "Royal Harvest", "food", False),
    ("wheat_atta_defective", "Whole Wheat Atta", "Golden Mill", "food", False),
    ("olive_oil_imported", "Extra Virgin Olive Oil", "Oliva Doro", "food", True),
    ("herbal_shampoo_cosmetic", "Herbal Shampoo", "Silken", "cosmetic", False),
    ("usb_charger_electronics", "USB Fast Charger 20W", "Voltex", "electronics", False),
]


def call(url, method="GET", data=None, token=None, headers=None):
    h = dict(headers or {})
    if token:
        h["Authorization"] = f"Bearer {token}"
    if isinstance(data, dict):
        data = json.dumps(data).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read() or b"{}")


def multipart(files, fields):
    boundary = uuid.uuid4().hex
    body = b""
    for name, value in fields:
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode()
    for name, path in files:
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{path.name}\"\r\n"
                 f"Content-Type: {ctype}\r\n\r\n").encode() + path.read_bytes() + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return body, {"Content-Type": f"multipart/form-data; boundary={boundary}"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--email", default="admin@safemetric.gov.in")
    ap.add_argument("--password", default="Admin@12345")
    a = ap.parse_args()
    token = call(f"{a.url}/api/auth/login", "POST", {"email": a.email, "password": a.password})["access_token"]
    for folder, name, brand, cat, imported in PRODUCTS:
        insp = call(f"{a.url}/api/inspections", "POST", {"product_name": name, "brand": brand, "category": cat,
                                                        "is_imported": imported, "all_panels_captured": True}, token)
        sides = sorted(p.stem for p in (SAMPLES / folder).glob("*.jpg"))
        body, h = multipart([("files", SAMPLES / folder / f"{s}.jpg") for s in sides], [("sides", s) for s in sides])
        call(f"{a.url}/api/inspections/{insp['id']}/images", "POST", body, token, h)
        r = call(f"{a.url}/api/inspections/{insp['id']}/analyze?sync=true", "POST", None, token)
        print(f"{r['reference']}  {name:28} {r['overall_status']:20} score {r['score']}%")


if __name__ == "__main__":
    main()
