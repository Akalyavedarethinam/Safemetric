"""Password hashing (bcrypt), JWT access tokens, role-based access dependencies, login throttling."""
from __future__ import annotations

import re
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import config
from .database import get_db
from .models import AuditLog, User

_bearer = HTTPBearer(auto_error=False)


# ------------------------------------------------------------------ passwords
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], hashed.encode())
    except ValueError:
        return False


def password_problems(password: str) -> str | None:
    if len(password) < 8:
        return "Password must be at least 8 characters long."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "Password must contain at least one letter and one number."
    return None


# ------------------------------------------------------------------ tokens
def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=config.ACCESS_TOKEN_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, config.SECRET_KEY, algorithm=config.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, config.SECRET_KEY, algorithms=[config.JWT_ALGORITHM])


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None or not creds.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required. Please sign in.")
    try:
        payload = decode_token(creds.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has expired. Please sign in again.")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid authentication token.")
    user = db.get(User, int(payload.get("sub", 0)))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account not found or deactivated.")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator privileges are required for this action.")
    return user


# ------------------------------------------------------------------ throttling
_attempts: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()
WINDOW_SECONDS = 15 * 60


def check_login_throttle(key: str) -> None:
    now = time.time()
    with _lock:
        q = _attempts[key]
        while q and now - q[0] > WINDOW_SECONDS:
            q.popleft()
        if len(q) >= config.LOGIN_MAX_ATTEMPTS:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                "Too many failed sign-in attempts. Please wait 15 minutes and try again.")


def record_failed_login(key: str) -> None:
    with _lock:
        _attempts[key].append(time.time())


def clear_login_failures(key: str) -> None:
    with _lock:
        _attempts.pop(key, None)


# ------------------------------------------------------------------ audit
def client_ip(request: Request | None) -> str:
    if request is None:
        return ""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""


def audit(db: Session, user: User | None, action: str, detail: str = "", request: Request | None = None) -> None:
    db.add(AuditLog(user_id=user.id if user else None, user_email=user.email if user else "",
                    action=action, detail=detail[:2000], ip=client_ip(request)))
    db.commit()
