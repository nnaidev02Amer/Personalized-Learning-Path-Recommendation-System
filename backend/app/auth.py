"""Authentication & authorisation dependencies.

Every API route except ``/api/health``, ``/api/auth/login``, ``/api/auth/register`` (when enabled) and
``/api/auth/config`` depends on :func:`current_principal`.

* Identity comes from an ``HttpOnly`` cookie holding a random token; the database stores only its hash.
* State-changing requests (POST/PUT/PATCH/DELETE) must also send the session's CSRF token in the
  ``X-CSRF-Token`` header, and any ``Origin`` header must be an allowed origin.
* Students may only reach their own student record; for every other student they get the same
  ``404 not found`` a non-existent id gets, so ids cannot be probed.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated
from urllib.parse import urlparse

from fastapi import Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.deps import get_db
from backend.app.errors import Forbidden, NotFound, Unauthorized
from backend.app.models import AuthSession, Enrollment, Student, User, utcnow
from backend.app.security import hash_token, new_token

COOKIE_NAME = "plrs_session"
CSRF_HEADER = "X-CSRF-Token"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
DB = Annotated[Session, Depends(get_db)]


@dataclass
class Principal:
    user: User
    session: AuthSession

    @property
    def is_admin(self) -> bool:
        return self.user.role == "admin"

    @property
    def student_id(self) -> int | None:
        return self.user.student_id


# ---------------------------------------------------------------- cookies / sessions
def create_session(db: Session, user: User, ttl_hours: float) -> tuple[str, AuthSession]:
    token = new_token()
    session = AuthSession(user_id=user.id, token_hash=hash_token(token), csrf_token=secrets.token_urlsafe(32),
                          expires_at=utcnow() + timedelta(hours=ttl_hours))
    db.add(session)
    # opportunistic clean-up of long-dead sessions
    for old in db.scalars(select(AuthSession).where(AuthSession.expires_at < utcnow() - timedelta(days=1))):
        db.delete(old)
    db.flush()
    return token, session


def set_session_cookie(request: Request, response: Response, token: str) -> None:
    settings = request.app.state.settings
    response.set_cookie(COOKIE_NAME, token, max_age=int(settings.session_ttl_hours * 3600), httponly=True,
                        samesite="lax", secure=settings.cookie_secure, path="/")


def clear_session_cookie(request: Request, response: Response) -> None:
    settings = request.app.state.settings
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="lax", secure=settings.cookie_secure)


def check_origin(request: Request) -> None:
    """Reject cross-site browser requests: an Origin header, when sent, must be an allowed origin."""
    origin = request.headers.get("origin")
    if not origin:
        return
    allowed = set(request.app.state.settings.cors_origins)
    host = urlparse(origin)
    same_host = host.netloc and host.netloc == request.headers.get("host")
    if origin not in allowed and not same_host:
        raise Forbidden("Cross-origin request blocked", code="origin_not_allowed")


def find_session(request: Request, db: Session) -> tuple[AuthSession, User] | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    now = utcnow()
    if session is None or session.revoked_at is not None or session.expires_at <= now:
        return None
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        return None
    return session, user


# ---------------------------------------------------------------- dependencies
def current_principal(request: Request, db: DB) -> Principal:
    found = find_session(request, db)
    if found is None:
        raise Unauthorized("Sign in to continue")
    session, user = found
    if request.method in UNSAFE_METHODS:
        check_origin(request)
        sent = request.headers.get(CSRF_HEADER, "")
        if not sent or not secrets.compare_digest(sent, session.csrf_token):
            raise Forbidden("Missing or invalid CSRF token", code="csrf_failed")
    return Principal(user=user, session=session)


PrincipalDep = Annotated[Principal, Depends(current_principal)]


def require_admin(principal: PrincipalDep) -> Principal:
    if not principal.is_admin:
        raise Forbidden("Administrator access required", code="admin_required")
    return principal


AdminDep = Annotated[Principal, Depends(require_admin)]


def student_scope(student_id: int, principal: PrincipalDep, db: DB) -> Student:
    """Path-parameter dependency: the student ``student_id``, if the caller may see it."""
    if not principal.is_admin and principal.student_id != student_id:
        raise NotFound(f"Student {student_id} not found")
    student = db.get(Student, student_id)
    if student is None:
        raise NotFound(f"Student {student_id} not found")
    return student


StudentDep = Annotated[Student, Depends(student_scope)]


def enrollment_scope(enrollment_id: int, principal: PrincipalDep, db: DB) -> Enrollment:
    enrollment = db.get(Enrollment, enrollment_id)
    if enrollment is None or (not principal.is_admin and enrollment.student_id != principal.student_id):
        raise NotFound(f"Enrollment {enrollment_id} not found")
    return enrollment


EnrollmentDep = Annotated[Enrollment, Depends(enrollment_scope)]
