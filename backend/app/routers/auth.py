"""Sign in / sign out / current user / (optional) self-registration."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from backend.app import schemas
from backend.app.auth import (DB, PrincipalDep, check_origin, clear_session_cookie, create_session,
                              current_principal, find_session, set_session_cookie)
from backend.app.errors import Conflict, Forbidden, Invalid, TooManyRequests, Unauthorized
from backend.app.models import Student, User, utcnow
from backend.app.security import hash_password, needs_rehash, password_problems, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$"
GENERIC_LOGIN_ERROR = "Incorrect e-mail or password"


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(max_length=255)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def _norm(cls, v: str) -> str:
        return v.strip().lower()


class RegisterRequest(schemas.StudentBase):
    """Self-registration. There is deliberately no ``student_id`` field: a new account always gets a
    brand-new learner profile and can never be attached to an existing one."""
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    role: str
    is_active: bool
    student_id: int | None
    created_at: datetime
    last_login_at: datetime | None


class SessionOut(BaseModel):
    user: UserOut
    student: schemas.StudentOut | None
    csrf_token: str
    expires_at: datetime


def session_payload(user: User, session) -> dict:
    return {"user": user, "student": user.student, "csrf_token": session.csrf_token,
            "expires_at": session.expires_at}


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _throttle(request: Request, key: str, limit: int, window: float, message: str) -> None:
    wait = request.app.state.limiter.hit(key, limit, window)
    if wait:
        raise TooManyRequests(message, retry_after=int(wait))


def _check_password(password: str, email: str, name: str | None = None) -> None:
    problems = password_problems(password, email=email, name=name)
    if problems:
        raise Invalid("Password is not acceptable", details=[{"field": "password", "message": p} for p in problems])


@router.get("/config")
def auth_config(request: Request):
    """Public: lets the sign-in page decide whether to offer registration."""
    return {"allow_self_registration": request.app.state.settings.allow_self_registration}


@router.post("/login", response_model=SessionOut)
def login(data: LoginRequest, request: Request, response: Response, db: DB):
    check_origin(request)
    settings = request.app.state.settings
    too_many = "Too many sign-in attempts. Please wait and try again."
    _throttle(request, f"login:ip:{_client_ip(request)}", 30, 60, too_many)
    _throttle(request, f"login:email:{data.email}", 10, 900, too_many)

    user = db.scalar(select(User).where(User.email == data.email))
    now = utcnow()
    if user is not None and user.locked_until and user.locked_until > now:
        raise TooManyRequests(too_many, retry_after=int((user.locked_until - now).total_seconds()) + 1)

    ok = verify_password(user.password_hash if user else None, data.password)
    if user is None or not ok:
        if user is not None:
            user.failed_logins += 1
            if user.failed_logins >= settings.max_failed_logins:
                user.failed_logins = 0
                user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
            db.commit()
        raise _bad_login()
    if not user.is_active:
        raise _bad_login()                               # same answer as a wrong password

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(data.password)
    user.failed_logins, user.locked_until, user.last_login_at = 0, None, now
    token, session = create_session(db, user, settings.session_ttl_hours)
    db.commit()
    request.app.state.limiter.reset(f"login:email:{data.email}")
    set_session_cookie(request, response, token)
    return session_payload(user, session)


def _bad_login() -> Unauthorized:
    exc = Unauthorized(GENERIC_LOGIN_ERROR)
    exc.code = "invalid_credentials"
    return exc


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: DB):
    """Revokes the current session. Always clears the cookie; CSRF-protected when a session exists."""
    found = find_session(request, db)
    if found is not None:
        principal = current_principal(request, db)       # enforces origin + CSRF token
        principal.session.revoked_at = utcnow()
        db.commit()
    out = Response(status_code=204)
    clear_session_cookie(request, out)
    return out


@router.get("/me", response_model=SessionOut)
def me(principal: PrincipalDep):
    return session_payload(principal.user, principal.session)


@router.post("/register", response_model=SessionOut, status_code=201)
def register(data: RegisterRequest, request: Request, response: Response, db: DB):
    settings = request.app.state.settings
    if not settings.allow_self_registration:
        raise Forbidden("Self-registration is disabled. Ask an administrator for an account.",
                        code="registration_disabled")
    check_origin(request)
    _throttle(request, f"register:ip:{_client_ip(request)}", 10, 3600,
              "Too many registrations from this address. Try again later.")
    _check_password(data.password, data.email, data.name)
    if db.scalar(select(User.id).where(User.email == data.email)) or \
            db.scalar(select(Student.id).where(Student.email == data.email)):
        raise Conflict("That e-mail address is already registered", code="email_taken")

    fields = data.model_dump(exclude={"password"})
    student = Student(**fields, is_synthetic=False)
    db.add(student)
    db.flush()
    user = User(email=data.email, password_hash=hash_password(data.password), role="student", student_id=student.id)
    db.add(user)
    db.flush()
    token, session = create_session(db, user, settings.session_ttl_hours)
    user.last_login_at = utcnow()
    db.commit()
    set_session_cookie(request, response, token)
    return session_payload(user, session)
