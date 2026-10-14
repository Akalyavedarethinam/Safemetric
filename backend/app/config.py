"""
Central configuration for SafeMetric.

Every setting is read from an environment variable (optionally loaded from a
`.env` file in the backend directory) so the same code runs on a laptop,
in Docker, or on any cloud platform.
"""
from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent          # backend/
PROJECT_DIR = BASE_DIR.parent                               # safemetric/


def _load_dotenv() -> None:
    """Tiny .env loader (avoids an extra dependency). Existing env vars win."""
    for candidate in (BASE_DIR / ".env", PROJECT_DIR / ".env"):
        if not candidate.exists():
            continue
        for raw in candidate.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    return env(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(env(name, str(default)))
    except ValueError:
        return default


APP_NAME = "SafeMetric"
APP_VERSION = "2.2.0"
ENVIRONMENT = env("ENVIRONMENT", "development")

# ---------------------------------------------------------------- storage paths
DATA_DIR = Path(env("DATA_DIR", str(BASE_DIR / "data")))
UPLOAD_DIR = Path(env("UPLOAD_DIR", str(DATA_DIR / "uploads")))
REPORT_DIR = DATA_DIR / "reports"
FRONTEND_DIST = Path(env("FRONTEND_DIST", str(PROJECT_DIR / "frontend" / "dist")))

# ---------------------------------------------------------------- database
DATABASE_URL = env("DATABASE_URL", f"sqlite:///{DATA_DIR / 'safemetric.db'}")
# Heroku/Render style URLs use postgres:// which SQLAlchemy 2 does not accept
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]

# ---------------------------------------------------------------- security
SECRET_KEY = env("SECRET_KEY", "dev-only-change-me-" + "x" * 24)
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = env_int("ACCESS_TOKEN_MINUTES", 480)
ALLOW_SELF_REGISTRATION = env_bool("ALLOW_SELF_REGISTRATION", True)
ALLOWED_ORIGINS = [o.strip() for o in env("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
LOGIN_MAX_ATTEMPTS = env_int("LOGIN_MAX_ATTEMPTS", 8)          # per email+IP per 15 minutes

DEFAULT_ADMIN_EMAIL = env("DEFAULT_ADMIN_EMAIL", "admin@safemetric.gov.in")
DEFAULT_ADMIN_PASSWORD = env("DEFAULT_ADMIN_PASSWORD", "Admin@12345")
DEFAULT_ADMIN_NAME = env("DEFAULT_ADMIN_NAME", "System Administrator")

ROLES = ("admin", "inspector")

# ---------------------------------------------------------------- uploads
MAX_UPLOAD_MB = env_int("MAX_UPLOAD_MB", 10)
MAX_IMAGES_PER_INSPECTION = env_int("MAX_IMAGES_PER_INSPECTION", 12)
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_EVIDENCE_EXT = ALLOWED_IMAGE_EXT | {".pdf"}
PACKAGE_SIDES = ("front", "back", "left", "right", "top", "bottom", "additional")

# ---------------------------------------------------------------- object storage
# STORAGE_BACKEND = local | s3 | azure
#   s3 covers AWS S3, Cloudflare R2, Supabase Storage (S3 API) and Google Cloud
#   Storage (S3 interoperability / HMAC keys) through S3_ENDPOINT_URL.
STORAGE_BACKEND = env("STORAGE_BACKEND", "local").lower()
S3_BUCKET = env("S3_BUCKET")
S3_ENDPOINT_URL = env("S3_ENDPOINT_URL") or None
S3_REGION = env("S3_REGION", "auto")
S3_ACCESS_KEY_ID = env("S3_ACCESS_KEY_ID")
S3_SECRET_ACCESS_KEY = env("S3_SECRET_ACCESS_KEY")
AZURE_CONNECTION_STRING = env("AZURE_STORAGE_CONNECTION_STRING")
AZURE_CONTAINER = env("AZURE_STORAGE_CONTAINER", "safemetric")


# ---------------------------------------------------------------- OCR
def _default_tesseract() -> str:
    found = shutil.which("tesseract")
    if found:
        return found
    if platform.system() == "Windows":
        return r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    return "/usr/bin/tesseract"


TESSERACT_CMD = env("TESSERACT_CMD", _default_tesseract())
OCR_LANG = env("OCR_LANG", "eng")
OCR_WORKERS = env_int("OCR_WORKERS", 3)                  # parallel Tesseract passes
OCR_MAX_SIDE = env_int("OCR_MAX_SIDE", 3000)             # downscale huge photos before OCR
OCR_MIN_SIDE = env_int("OCR_MIN_SIDE", 1600)             # upscale small photos before OCR
OCR_PASS_TIMEOUT = env_int("OCR_PASS_TIMEOUT", 90)       # seconds per Tesseract pass
# OCR engine:  ppocr     = PP-OCR text detection + recognition (default - best measured CER / field F1, fastest);
#                          Tesseract is used automatically if PP-OCR is not installed
#              hybrid    = PP-OCR AND a reduced set of Tesseract passes, merged (slower, not better on the test set)
#              tesseract = the original v2.1 multi-pass Tesseract pipeline only
# (see PROJECT_REPORT.md for the measured comparison)
OCR_ENGINE = env("OCR_ENGINE", "ppocr").strip().lower()
PPOCR_MODEL_DIR = env("PPOCR_MODEL_DIR", str(PROJECT_DIR / "models" / "ocr" / "ppocrv5"))
# number of Tesseract passes (from the top of ocr.PASS_PLAN) used in hybrid mode
OCR_HYBRID_TESSERACT_PASSES = env_int("OCR_HYBRID_TESSERACT_PASSES", 3)
# bonus added to PP-OCR lines when hybrid merging chooses between overlapping readings (0 = confidence only)
OCR_HYBRID_PPOCR_BONUS = float(env("OCR_HYBRID_PPOCR_BONUS", "0"))
# page orientation/deskew: auto = PP-OCR text-line geometry, falling back to Tesseract OSD + projection deskew
OCR_GEOMETRY = env("OCR_GEOMETRY", "auto").strip().lower()
PPOCR_USE_CLS = env_bool("PPOCR_USE_CLS", False)            # per-line 180° classifier (page is already upright)
PPOCR_BOX_THRESH = float(env("PPOCR_BOX_THRESH", "0.5"))    # DB detector box score threshold
PPOCR_UNCLIP = float(env("PPOCR_UNCLIP", "1.6"))            # DB detector box expansion ratio
PPOCR_MIN_SCORE = float(env("PPOCR_MIN_SCORE", "0.45"))     # drop recognised lines below this confidence
PPOCR_DET_LIMIT = env_int("PPOCR_DET_LIMIT", 736)          # detector input: shorter side resized to this
PPOCR_ENHANCE = env("PPOCR_ENHANCE", "auto").strip().lower()
# extra pass on a 2x upscaled + sharpened copy when the photo is blurred (Laplacian variance below the threshold)
PPOCR_DEBLUR = env("PPOCR_DEBLUR", "auto").strip().lower()      # auto | always | off
PPOCR_BLUR_THRESHOLD = float(env("PPOCR_BLUR_THRESHOLD", "150"))  # auto | always | off : extra pass on a contrast-enhanced copy
OCR_TEXT_CLEAN = env_bool("OCR_TEXT_CLEAN", True)          # context-safe post-OCR clean-up (raw text is kept)
# trained line-role model (brand / product name): portable numpy export (.npz + .json, no scikit-learn needed).
# Missing file = layout heuristic instead.
LINE_ROLE_MODEL = env("LINE_ROLE_MODEL", str(PROJECT_DIR / "models" / "extraction" / "line_role_model.npz"))

# ---------------------------------------------------------------- Rule 27 registration verification
REGISTRATION_API_URL = env("REGISTRATION_API_URL")       # optional authoritative registry endpoint
REGISTRATION_API_KEY = env("REGISTRATION_API_KEY")

for _d in (DATA_DIR, UPLOAD_DIR, REPORT_DIR):
    _d.mkdir(parents=True, exist_ok=True)
