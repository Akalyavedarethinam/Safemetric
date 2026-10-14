"""
SafeMetric - Legal Metrology (Packaged Commodities) compliance inspection API.

Run locally:  uvicorn app.main:app --reload     (from the backend/ directory)
The built React frontend (frontend/dist) is served from the same origin when present.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from . import config
from .database import Base, SessionLocal, engine
from .models import Inspection, User
from .routers import auth, inspections, misc
from .routers import ocr as ocr_router
from .security import hash_password

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("safemetric")


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if not db.query(User).filter(func.lower(User.email) == config.DEFAULT_ADMIN_EMAIL.lower()).first():
            db.add(User(name=config.DEFAULT_ADMIN_NAME, email=config.DEFAULT_ADMIN_EMAIL.lower(),
                        password_hash=hash_password(config.DEFAULT_ADMIN_PASSWORD), role="admin",
                        designation="Controller, Legal Metrology"))
            log.warning("Seeded default administrator %s - change its password after first sign-in.",
                        config.DEFAULT_ADMIN_EMAIL)
        # analyses interrupted by a restart can never finish - mark them failed so they can be re-run
        for insp in db.query(Inspection).filter(Inspection.status == "PROCESSING"):
            insp.status, insp.stage = "FAILED", "FAILED"
            insp.error = "Analysis was interrupted by a server restart. Please run the analysis again."
        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if config.SECRET_KEY.startswith("dev-only") and config.ENVIRONMENT == "production":
        log.error("SECRET_KEY is not set - refusing to run in production with the development key.")
        raise RuntimeError("Set SECRET_KEY for production deployments.")
    init_db()
    yield


app = FastAPI(title="SafeMetric API", version=config.APP_VERSION, lifespan=lifespan,
              description="Automated Legal Metrology (Packaged Commodities) Rules, 2011 compliance inspection.")

app.add_middleware(CORSMiddleware, allow_origins=config.ALLOWED_ORIGINS, allow_credentials=False,
                   allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["Content-Disposition"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(self), microphone=()")
    return response


# ---------------------------------------------------------------- friendly errors (no stack traces to users)
@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException):
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    msgs = []
    for e in exc.errors()[:5]:
        loc = ".".join(str(x) for x in e.get("loc", []) if x not in ("body", "query", "path"))
        msgs.append(f"{loc}: {e.get('msg')}" if loc else e.get("msg"))
    return JSONResponse({"detail": "Invalid input - " + "; ".join(msgs)}, status_code=422)


@app.exception_handler(OperationalError)
async def db_down(_: Request, exc: OperationalError):
    log.error("database error: %s", exc)
    return JSONResponse({"detail": "The database is temporarily unavailable. Please try again shortly."}, status_code=503)


@app.exception_handler(SQLAlchemyError)
async def db_error(_: Request, exc: SQLAlchemyError):
    log.exception("database failure")
    return JSONResponse({"detail": "A database error occurred. The details were logged on the server."}, status_code=500)


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    log.exception("unhandled error")
    return JSONResponse({"detail": "An unexpected error occurred. The details were logged on the server."}, status_code=500)


app.include_router(auth.router)
app.include_router(inspections.router)
app.include_router(misc.router)
app.include_router(ocr_router.router)


# ---------------------------------------------------------------- single-page frontend
if (config.FRONTEND_DIST / "index.html").exists():
    assets = config.FRONTEND_DIST / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        candidate = (config.FRONTEND_DIST / full_path).resolve()
        if full_path and candidate.is_file() and config.FRONTEND_DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(config.FRONTEND_DIST / "index.html")
else:
    @app.get("/", include_in_schema=False)
    def root():
        return {"app": "SafeMetric API", "docs": "/docs",
                "frontend": "Build the frontend (cd frontend && npm install && npm run build) to serve the UI here."}
