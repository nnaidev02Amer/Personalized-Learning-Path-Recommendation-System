from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.app import schemas, services
from backend.app.deps import get_db
from backend.app.errors import Conflict, Invalid
from backend.app.models import ActivityLog, Course, QuizAttempt, Student

router = APIRouter(prefix="/api/students", tags=["students"])
DB = Annotated[Session, Depends(get_db)]


def _email_taken(db: Session, email: str, exclude_id: int | None = None) -> None:
    stmt = select(Student.id).where(Student.email == email)
    if exclude_id is not None:
        stmt = stmt.where(Student.id != exclude_id)
    if db.scalar(stmt) is not None:
        raise Conflict(f"Email {email} is already registered", code="email_taken")


@router.get("", response_model=schemas.Page[schemas.StudentOut])
def list_students(db: DB, search: str | None = Query(None, max_length=100),
                  learning_style: schemas.LearningStyle | None = None,
                  limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    stmt = select(Student)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(Student.name.ilike(like), Student.email.ilike(like)))
    if learning_style:
        stmt = stmt.where(Student.learning_style == learning_style)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = db.scalars(stmt.order_by(Student.id).limit(limit).offset(offset)).all()
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.post("", response_model=schemas.StudentOut, status_code=201)
def create_student(data: schemas.StudentCreate, db: DB):
    _email_taken(db, data.email)
    student = Student(**data.model_dump(), is_synthetic=False)
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


@router.get("/{student_id}", response_model=schemas.StudentOut)
def get_student(student_id: int, db: DB):
    return services.get_or_404(db, Student, student_id)


@router.patch("/{student_id}", response_model=schemas.StudentOut)
def update_student(student_id: int, data: schemas.StudentUpdate, db: DB):
    student = services.get_or_404(db, Student, student_id)
    changes = data.model_dump(exclude_unset=True)
    for field in ("name", "email", "age", "preferred_content", "daily_goal_minutes"):
        if field in changes and changes[field] is None:
            raise Invalid(f"{field} cannot be null")
    if "email" in changes:
        _email_taken(db, changes["email"].strip().lower(), exclude_id=student_id)
        changes["email"] = changes["email"].strip().lower()
    for key, value in changes.items():
        setattr(student, key, value)
    db.commit()
    return student


@router.delete("/{student_id}", status_code=204)
def delete_student(student_id: int, db: DB):
    db.delete(services.get_or_404(db, Student, student_id))
    db.commit()
    return Response(status_code=204)


@router.get("/{student_id}/summary", response_model=schemas.StudentSummary)
def student_summary(student_id: int, db: DB):
    return services.student_summary(db, services.get_or_404(db, Student, student_id))


@router.get("/{student_id}/progress", response_model=schemas.ProgressReport)
def student_progress(student_id: int, db: DB, weeks: int = Query(12, ge=1, le=52)):
    return services.progress_report(db, services.get_or_404(db, Student, student_id), weeks)


@router.get("/{student_id}/quiz-attempts", response_model=list[schemas.QuizAttemptOut])
def list_attempts(student_id: int, db: DB, limit: int = Query(50, ge=1, le=500)):
    services.get_or_404(db, Student, student_id)
    attempts = db.scalars(select(QuizAttempt).where(QuizAttempt.student_id == student_id)
                          .order_by(QuizAttempt.attempted_at.desc()).limit(limit)).all()
    return [services.attempt_out(a) for a in attempts]


@router.get("/{student_id}/activity", response_model=list[schemas.ActivityOut])
def list_activity(student_id: int, db: DB, limit: int = Query(100, ge=1, le=1000)):
    services.get_or_404(db, Student, student_id)
    return db.scalars(select(ActivityLog).where(ActivityLog.student_id == student_id)
                      .order_by(ActivityLog.activity_date.desc(), ActivityLog.id.desc())
                      .limit(limit)).all()


@router.post("/{student_id}/activity", response_model=schemas.ActivityOut, status_code=201)
def log_activity(student_id: int, data: schemas.ActivityCreate, db: DB):
    from datetime import date
    services.get_or_404(db, Student, student_id)
    if data.course_id is not None:
        services.get_or_404(db, Course, data.course_id)
    entry = ActivityLog(student_id=student_id, course_id=data.course_id, minutes=data.minutes,
                        activity_date=data.activity_date or date.today(), kind="study")
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
