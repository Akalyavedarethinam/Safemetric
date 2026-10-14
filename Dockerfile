# ---------- stage 1: build the React frontend ----------
FROM node:20-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- stage 2: Python API + PP-OCR (ONNX) + Tesseract OCR ----------
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    TESSERACT_CMD=/usr/bin/tesseract \
    DATA_DIR=/data \
    FRONTEND_DIST=/app/frontend/dist \
    ENVIRONMENT=production
# The Tesseract executable + English and orientation (osd) models + DejaVu fonts (₹ glyph in PDFs)
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-eng tesseract-ocr-osd fonts-dejavu-core libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
# pretrained PP-OCRv5 detector / recogniser + the trained line-role model
COPY models/ /app/models/
COPY --from=frontend /app/frontend/dist /app/frontend/dist
RUN useradd -m -u 10001 safemetric && mkdir -p /data && chown -R safemetric /data /app
USER safemetric
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:'+__import__('os').environ.get('PORT','8000')+'/api/health')" || exit 1
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
