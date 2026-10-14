from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import config
from ..database import get_db
from ..models import User, utcnow
from ..security import (audit, check_login_throttle, clear_login_failures, client_ip, create_access_token,
                        get_current_user, hash_password, password_problems, record_failed_login, verify_password)
from ..serializers import user_out

router = APIRouter(prefix="/api/auth", tags=["auth"])
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class LoginIn(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)
    designation: str = Field(default="Inspector, Legal Metrology", max_length=120)
    jurisdiction: str = Field(default="", max_length=160)
    phone: str = Field(default="", max_length=30)


class ProfileIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    designation: str = Field(default="", max_length=120)
    jurisdiction: str = Field(default="", max_length=160)
    phone: str = Field(default="", max_length=30)


class PasswordIn(BaseModel):
    current_password: str
    new_password: str


def _token_response(user: User) -> dict:
    return {"access_token": create_access_token(user), "token_type": "bearer",
            "expires_in": config.ACCESS_TOKEN_MINUTES * 60, "user": user_out(user)}


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    key = f"{email}|{client_ip(request)}"
    check_login_throttle(key)
    user = db.query(User).filter(func.lower(User.email) == email).first()
    if not user or not verify_password(body.password, user.password_hash):
        record_failed_login(key)
        audit(db, None, "LOGIN_FAILED", email, request)
        raise HTTPException(401, "Invalid email or password.")
    if not user.is_active:
        raise HTTPException(403, "This account has been deactivated. Contact the administrator.")
    clear_login_failures(key)
    user.last_login = utcnow()
    db.commit()
    audit(db, user, "LOGIN", "", request)
    return _token_response(user)


@router.post("/register", status_code=201)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    if not config.ALLOW_SELF_REGISTRATION:
        raise HTTPException(403, "Self-registration is disabled. Ask an administrator to create your account.")
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(422, "Please enter a valid email address.")
    problem = password_problems(body.password)
    if problem:
        raise HTTPException(422, problem)
    if db.query(User).filter(func.lower(User.email) == email).first():
        raise HTTPException(409, "An account with this email already exists.")
    user = User(name=body.name.strip(), email=email, password_hash=hash_password(body.password), role="inspector",
                designation=body.designation, jurisdiction=body.jurisdiction, phone=body.phone, last_login=utcnow())
    db.add(user)
    db.commit()
    audit(db, user, "REGISTER", "self-registration", request)
    return _token_response(user)


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return user_out(user)


@router.put("/me")
def update_me(body: ProfileIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.name, user.designation, user.jurisdiction, user.phone = body.name.strip(), body.designation, body.jurisdiction, body.phone
    db.commit()
    return user_out(user)


@router.post("/change-password")
def change_password(body: PasswordIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect.")
    problem = password_problems(body.new_password)
    if problem:
        raise HTTPException(422, problem)
    user.password_hash = hash_password(body.new_password)
    db.commit()
    audit(db, user, "PASSWORD_CHANGED", "", request)
    return {"ok": True}


@router.post("/logout")
def logout(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    audit(db, user, "LOGOUT", "", request)
    return {"ok": True}
