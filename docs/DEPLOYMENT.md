# Deployment Guide

## 1. Requirements

| Component | Development | Production |
|---|---|---|
| Python | 3.10+ | 3.11 (Docker image) |
| Node | 18+ (only to rebuild the UI) | only at image build time |
| Tesseract OCR | local install | `apt-get install tesseract-ocr tesseract-ocr-eng tesseract-ocr-osd` (in the Dockerfile) |
| Database | SQLite (automatic) | PostgreSQL 13+ |
| File storage | `backend/data/uploads` | persistent disk **or** S3-compatible / Azure object storage |

> **Tesseract:** `pip install pytesseract` installs only the Python wrapper, not the OCR engine.
> Since v2.2 the default OCR engine is PP-OCR (`pip install rapidocr_onnxruntime`, models in `models/ocr/`).
> Tesseract is still recommended as the fallback and for `OCR_ENGINE=tesseract|hybrid`.
> Install the executable and point `TESSERACT_CMD` at it. Without it, `/api/health` reports
> `"ocr": {"available": false}`, the UI shows "OCR engine unavailable", and analysis returns
> *"Tesseract OCR is unavailable. Please configure TESSERACT_CMD."*

## 2. Environment variables

See `backend/.env.example` for the full list. The essential ones:

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | JWT signing key. **Required** when `ENVIRONMENT=production`. |
| `DATABASE_URL` | `postgresql://user:pass@host:5432/db`. `postgres://` URLs are accepted. |
| `TESSERACT_CMD` | Path to the tesseract binary (`/usr/bin/tesseract` or `C:\Program Files\Tesseract-OCR\tesseract.exe`) |
| `STORAGE_BACKEND` | `local` · `s3` · `azure` |
| `S3_BUCKET`, `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_REGION` | Object storage |
| `ALLOWED_ORIGINS` | Comma-separated list of origins, if the UI is hosted on another domain |
| `DEFAULT_ADMIN_EMAIL` / `DEFAULT_ADMIN_PASSWORD` | Administrator seeded on first start |
| `ALLOW_SELF_REGISTRATION` | `false` to allow only admin-created accounts |
| `MAX_UPLOAD_MB`, `MAX_IMAGES_PER_INSPECTION`, `OCR_WORKERS` | Limits and tuning |
| `OCR_ENGINE` | `ppocr` (default: PP-OCRv5 detection + recognition; falls back to Tesseract if it is not installed) · `hybrid` · `tesseract` (original v2.1 pipeline) |
| `PPOCR_MODEL_DIR` | folder with `det.onnx` / `rec.onnx` (default `models/ocr/ppocrv5`). If missing, the PP-OCRv4 models bundled in `rapidocr_onnxruntime` are used |
| `PPOCR_ENHANCE` | `auto` (default: a second pass on a contrast-enhanced copy for dark / low-contrast photos) · `always` · `off` |
| `OCR_GEOMETRY` | `auto` (default: straighten with PP-OCR text-line geometry, any angle) · `legacy` (Tesseract OSD + ±8° deskew) |
| `OCR_TEXT_CLEAN` | `true` (default): context-safe post-OCR clean-up. The raw text is always stored as well |
| `LINE_ROLE_MODEL` | path of the trained brand / product-name model (default `models/extraction/line_role_model.joblib`) |

## 3. Docker (any cloud)

```bash
docker build -t safemetric .
docker run -p 8000:8000 \
  -e SECRET_KEY="$(python -c 'import secrets;print(secrets.token_urlsafe(48))')" \
  -e DATABASE_URL=postgresql://... \
  -v safemetric-data:/data safemetric
```
The image builds the React UI, installs Tesseract (eng + osd) and DejaVu fonts (for ₹ in PDFs), runs as a non-root user, listens
on `$PORT` (default 8000) and has a `/api/health` health check.

`docker compose up --build` starts the app together with PostgreSQL.

## 4. Platform recipes

**Render.** Push to GitHub, then choose *New → Blueprint* and select `render.yaml`. This creates the web service, the PostgreSQL database and a persistent disk.
Set `DEFAULT_ADMIN_PASSWORD` in the dashboard.

**Railway / Fly.io / Google Cloud Run / Azure Container Apps / AWS App Runner.** Deploy the Dockerfile. Attach a
managed PostgreSQL database and set `DATABASE_URL`. Use `STORAGE_BACKEND=s3` (or `azure`), because container file systems on these platforms are
ephemeral.

**Object storage examples**

| Provider | Settings |
|---|---|
| AWS S3 | `S3_BUCKET=my-bucket`, `S3_REGION=ap-south-1`, access keys |
| Cloudflare R2 | `S3_ENDPOINT_URL=https://<account>.r2.cloudflarestorage.com`, `S3_REGION=auto` |
| Supabase Storage | `S3_ENDPOINT_URL=https://<project>.supabase.co/storage/v1/s3`, S3 access keys from the dashboard |
| Google Cloud Storage | `S3_ENDPOINT_URL=https://storage.googleapis.com`, HMAC interoperability keys |
| Azure Blob | `STORAGE_BACKEND=azure`, `AZURE_STORAGE_CONNECTION_STRING`, `pip install azure-storage-blob` |

**A plain VM (Ubuntu).**
```bash
sudo apt install python3-venv tesseract-ocr tesseract-ocr-eng tesseract-ocr-osd postgresql nginx
cd /opt/safemetric/backend && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
# systemd unit: ExecStart=/opt/safemetric/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers
# nginx: reverse-proxy https → 127.0.0.1:8000, client_max_body_size 50m;
```

**Split hosting** (UI on Netlify/Vercel, API elsewhere): build the UI with `VITE_API_BASE=https://api.example.com npm run build`,
and set `ALLOWED_ORIGINS=https://ui.example.com` on the API.

## 5. Operations

* **Scaling.** Analysis runs in background threads inside the API process. For high volume, run several containers behind a load
  balancer with a shared PostgreSQL database and shared object storage. `OCR_WORKERS` controls the number of parallel Tesseract passes per image.
* **Schema.** Tables are created automatically at start-up (`create_all`). For future schema changes, add Alembic.
* **Backups.** Back up PostgreSQL and the storage bucket or volume. Each inspection's integrity hash lets you detect later tampering.
* **Security checklist.** Set a strong `SECRET_KEY`, change the admin password, serve over HTTPS, set `ALLOW_SELF_REGISTRATION=false`
  for closed deployments, and restrict `ALLOWED_ORIGINS`.
* **Logs.** Standard output, in the format `safemetric.*` loggers. Unhandled errors are logged with a stack trace, while users see a generic message.
