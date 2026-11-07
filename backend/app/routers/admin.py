"""Administrator-only endpoints: overview, student monitoring and login-account management."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from backend.app import schemas
from backend.app.auth import AdminDep
from backend.app.deps import get_db
from backend.app.errors import Conflict, Forbidden, Invalid
from backend.app.models import (ActivityLog, AuthSession, Course, Enrollment, EnrollmentRequest, Quiz, QuizAttempt, Student, User,
                                utcnow)
from backend.app.routers.auth import UserOut, _check_password
from backend.app.security import hash_password
from backend.app import services

router = APIRouter(prefix="/api/admin", tags=["admin"])
DB = Annotated[Session, Depends(get_db)]
AT_RISK_AVERAGE = 60.0
AT_RISK_MIN_ATTEMPTS = 3


# ---------------------------------------------------------------- schemas
class StudentAccountCreate(schemas.StudentBase):
    """A new learner profile together with its login."""
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=1, max_length=256)


class LinkAccount(BaseModel):
    """Give an existing learner profile (e.g. a seeded student) a login. The login e-mail is the profile's."""
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=1, max_length=256)


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=1, max_length=256)
    unlock: bool | None = None

    @field_validator("is_active", "unlock")
    @classmethod
    def _not_null(cls, v):
        return v


class AdminUserOut(UserOut):
    student_name: str | None = None
    locked: bool = False
    active_sessions: int = 0


class StudentRow(BaseModel):
    id: int
    name: str
    email: str
    is_synthetic: bool
    has_login: bool
    enrollments: int
    active_enrollments: int
    completed_enrollments: int
    quiz_attempts: int
    average_score: float | None
    last_attempt_at: datetime | None
    at_risk: bool


# ---------------------------------------------------------------- helpers
def _user_out(db: Session, user: User) -> dict:
    sessions = db.scalar(select(func.count(AuthSession.id)).where(
        AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None), AuthSession.expires_at > utcnow()))
    return {**UserOut.model_validate(user).model_dump(), "student_name": user.student.name if user.student else None,
            "locked": bool(user.locked_until and user.locked_until > utcnow()), "active_sessions": sessions}


def revoke_sessions(db: Session, user_id: int) -> None:
    db.execute(update(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
               .values(revoked_at=utcnow()))


def _email_free(db: Session, email: str) -> None:
    if db.scalar(select(User.id).where(User.email == email)) or db.scalar(select(Student.id).where(Student.email == email)):
        raise Conflict(f"Email {email} is already registered", code="email_taken")


# ---------------------------------------------------------------- overview & monitoring
@router.get("/overview")
def overview(_admin: AdminDep, db: DB):
    now = utcnow()
    count = lambda stmt: db.scalar(stmt) or 0  # noqa: E731
    by_status = dict(db.execute(select(Enrollment.status, func.count()).group_by(Enrollment.status)).all())
    avg_score = db.scalar(select(func.avg(QuizAttempt.score)))
    top = db.execute(select(Course.id, Course.code, Course.title, func.count(Enrollment.id).label("n"))
                     .join(Enrollment, Enrollment.course_id == Course.id).group_by(Course.id)
                     .order_by(func.count(Enrollment.id).desc(), Course.code).limit(5)).all()
    return {
        "students": {"total": count(select(func.count(Student.id))),
                     "registered": count(select(func.count(User.id)).where(User.role == "student")),
                     "with_login": count(select(func.count(User.id)).where(User.role == "student")),
                     "seeded": count(select(func.count(Student.id)).where(Student.is_synthetic.is_(True))),
                     "registered_last_7_days": count(select(func.count(User.id)).where(
                         User.role == "student", User.created_at >= now - timedelta(days=7)))},
        "requests": {k: count(select(func.count(EnrollmentRequest.id)).where(EnrollmentRequest.status == k))
                     for k in ("pending", "approved", "rejected")},
        "admins": count(select(func.count(User.id)).where(User.role == "admin", User.is_active.is_(True))),
        "courses": {"active": count(select(func.count(Course.id)).where(Course.is_active.is_(True))),
                    "archived": count(select(func.count(Course.id)).where(Course.is_active.is_(False)))},
        "enrollments": {"total": sum(by_status.values()), **{k: by_status.get(k, 0) for k in ("active", "completed", "dropped")}},
        "quiz_attempts": {"total": count(select(func.count(QuizAttempt.id))),
                          "average_score": round(avg_score, 1) if avg_score is not None else None},
        "minutes_logged": round(count(select(func.coalesce(func.sum(ActivityLog.minutes), 0))), 1),
        "top_courses": [{"course_id": r.id, "code": r.code, "title": r.title, "enrollments": r.n} for r in top],
        "at_risk_students": count(_students_stmt(at_risk_only=True).with_only_columns(func.count()).order_by(None)),
    }


def _students_stmt(search: str | None = None, at_risk_only: bool = False):
    attempts = (select(QuizAttempt.student_id.label("sid"), func.count().label("n"),
                       func.avg(QuizAttempt.score).label("avg"), func.max(QuizAttempt.attempted_at).label("last"))
                .group_by(QuizAttempt.student_id).subquery())
    enrol = (select(Enrollment.student_id.label("sid"), func.count().label("n"),
                    func.sum(func.iif(Enrollment.status == "active", 1, 0)).label("active"),
                    func.sum(func.iif(Enrollment.status == "completed", 1, 0)).label("done"))
             .group_by(Enrollment.student_id).subquery())
    stmt = (select(Student.id, Student.name, Student.email, Student.is_synthetic,
                   func.coalesce(enrol.c.n, 0).label("enrollments"), func.coalesce(enrol.c.active, 0).label("active"),
                   func.coalesce(enrol.c.done, 0).label("done"), func.coalesce(attempts.c.n, 0).label("attempts"),
                   attempts.c.avg.label("avg"), attempts.c.last.label("last"),
                   select(func.count(User.id)).where(User.student_id == Student.id).scalar_subquery().label("logins"))
            .outerjoin(attempts, attempts.c.sid == Student.id).outerjoin(enrol, enrol.c.sid == Student.id))
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(Student.name.ilike(like), Student.email.ilike(like)))
    if at_risk_only:
        stmt = stmt.where(attempts.c.n >= AT_RISK_MIN_ATTEMPTS, attempts.c.avg < AT_RISK_AVERAGE)
    return stmt


@router.get("/students", response_model=schemas.Page[StudentRow])
def list_students(_admin: AdminDep, db: DB, search: str | None = Query(None, max_length=100),
                  at_risk: bool = False, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    """All learners with enrolment and performance totals (the monitoring table)."""
    stmt = _students_stmt(search, at_risk)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(stmt.order_by(Student.id).limit(limit).offset(offset)).all()
    items = [StudentRow(id=r.id, name=r.name, email=r.email, is_synthetic=r.is_synthetic, has_login=bool(r.logins),
                        enrollments=r.enrollments, active_enrollments=int(r.active), completed_enrollments=int(r.done),
                        quiz_attempts=r.attempts, average_score=round(r.avg, 1) if r.avg is not None else None,
                        last_attempt_at=r.last,
                        at_risk=bool(r.attempts >= AT_RISK_MIN_ATTEMPTS and r.avg is not None and r.avg < AT_RISK_AVERAGE))
             for r in rows]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/course-enrollments")
def course_enrollments(_admin: AdminDep, db: DB):
    """Every course with how many students are enrolled and how many requests wait for a decision."""
    enrolled = {r.course_id: r for r in db.execute(
        select(Enrollment.course_id, func.count().label("total"),
               func.sum(func.iif(Enrollment.status == "active", 1, 0)).label("active"),
               func.sum(func.iif(Enrollment.status == "completed", 1, 0)).label("done"))
        .group_by(Enrollment.course_id))}
    pending = dict(db.execute(select(EnrollmentRequest.course_id, func.count()).where(
        EnrollmentRequest.status == "pending").group_by(EnrollmentRequest.course_id)).all())
    out = []
    for c in db.scalars(select(Course).order_by(Course.topic, Course.level, Course.code)):
        e = enrolled.get(c.id)
        out.append({"course_id": c.id, "code": c.code, "title": c.title, "is_active": c.is_active,
                    "enrolled": e.total if e else 0, "active": int(e.active or 0) if e else 0,
                    "completed": int(e.done or 0) if e else 0, "pending_requests": pending.get(c.id, 0)})
    return out


# ---------------------------------------------------------------- enrolment requests
@router.get("/enrollment-requests", response_model=schemas.Page[schemas.EnrollmentRequestOut])
def list_requests(_admin: AdminDep, db: DB, status: schemas.RequestStatus | None = Query(None),
                  search: str | None = Query(None, max_length=100),
                  limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    stmt = select(EnrollmentRequest)
    if status:
        stmt = stmt.where(EnrollmentRequest.status == status)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(EnrollmentRequest.student_id.in_(select(Student.id).where(
            or_(Student.name.ilike(like), Student.email.ilike(like)))) | EnrollmentRequest.course_id.in_(
            select(Course.id).where(or_(Course.title.ilike(like), Course.code.ilike(like)))))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(EnrollmentRequest.requested_at.desc(), EnrollmentRequest.id.desc())
                      .limit(limit).offset(offset)).unique().all()
    return {"items": [services.request_out(r) for r in rows], "total": total, "limit": limit, "offset": offset}


@router.post("/enrollment-requests/{request_id}/approve", response_model=schemas.EnrollmentRequestOut)
def approve_request(request_id: int, admin: AdminDep, db: DB):
    request = services.get_or_404(db, EnrollmentRequest, request_id)
    return services.request_out(services.decide_request(db, request, True, admin.user.id))


@router.post("/enrollment-requests/{request_id}/reject", response_model=schemas.EnrollmentRequestOut)
def reject_request(request_id: int, admin: AdminDep, db: DB, data: schemas.RequestDecision | None = None):
    request = services.get_or_404(db, EnrollmentRequest, request_id)
    return services.request_out(services.decide_request(db, request, False, admin.user.id,
                                                         data.note if data else None))


# ---------------------------------------------------------------- accounts
@router.get("/users", response_model=schemas.Page[AdminUserOut])
def list_users(_admin: AdminDep, db: DB, role: str | None = Query(None, pattern="^(admin|student)$"),
               search: str | None = Query(None, max_length=100),
               limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    stmt = select(User)
    if role:
        stmt = stmt.where(User.role == role)
    if search:
        stmt = stmt.where(User.email.ilike(f"%{search.strip()}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    users = db.scalars(stmt.order_by(User.id).limit(limit).offset(offset)).all()
    return {"items": [_user_out(db, u) for u in users], "total": total, "limit": limit, "offset": offset}


@router.post("/users", response_model=AdminUserOut, status_code=201)
def create_student_account(_admin: AdminDep, data: StudentAccountCreate, db: DB):
    """Create a brand-new learner profile and its login."""
    _check_password(data.password, data.email, data.name)
    _email_free(db, data.email)
    student = Student(**data.model_dump(exclude={"password"}), is_synthetic=False)
    db.add(student)
    db.flush()
    user = User(email=data.email, password_hash=hash_password(data.password), role="student", student_id=student.id)
    db.add(user)
    db.commit()
    return _user_out(db, user)


@router.post("/students/{student_id}/account", response_model=AdminUserOut, status_code=201)
def link_account(student_id: int, _admin: AdminDep, data: LinkAccount, db: DB):
    """Attach a login to an EXISTING learner profile (the only way a login is tied to existing records)."""
    student = services.get_or_404(db, Student, student_id)
    if db.scalar(select(User.id).where(User.student_id == student_id)):
        raise Conflict("This student already has a login", code="account_exists")
    if db.scalar(select(User.id).where(User.email == student.email)):
        raise Conflict(f"Email {student.email} is already used by another login", code="email_taken")
    _check_password(data.password, student.email, student.name)
    user = User(email=student.email, password_hash=hash_password(data.password), role="student", student_id=student.id)
    db.add(user)
    db.commit()
    return _user_out(db, user)


@router.patch("/users/{user_id}", response_model=AdminUserOut)
def update_user(user_id: int, admin: AdminDep, data: UserUpdate, db: DB):
    user = services.get_or_404(db, User, user_id)
    changes = data.model_dump(exclude_unset=True)
    if any(v is None for v in changes.values()):
        raise Invalid("Fields cannot be null")
    if changes.get("is_active") is False:
        if user.id == admin.user.id:
            raise Forbidden("You cannot deactivate your own account", code="cannot_deactivate_self")
        others = db.scalar(select(func.count(User.id)).where(User.role == "admin", User.is_active.is_(True),
                                                             User.id != user.id))
        if user.role == "admin" and not others:
            raise Forbidden("The last active administrator cannot be deactivated", code="last_admin")
    if "password" in changes:
        _check_password(changes["password"], user.email, user.student.name if user.student else None)
        user.password_hash = hash_password(changes["password"])
        revoke_sessions(db, user.id)                              # old sessions must not survive a reset
    if "is_active" in changes:
        user.is_active = changes["is_active"]
        if not user.is_active:
            revoke_sessions(db, user.id)
    if changes.get("unlock"):
        user.failed_logins, user.locked_until = 0, None
    db.commit()
    return _user_out(db, user)


@router.post("/users/{user_id}/revoke-sessions", status_code=204)
def revoke_user_sessions(user_id: int, _admin: AdminDep, db: DB):
    from fastapi import Response
    services.get_or_404(db, User, user_id)
    revoke_sessions(db, user_id)
    db.commit()
    return Response(status_code=204)
