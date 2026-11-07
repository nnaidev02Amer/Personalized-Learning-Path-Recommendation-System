"""Enrolments, lesson progress and quizzes."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app import schemas, services
from backend.app.auth import EnrollmentDep, PrincipalDep, StudentDep
from backend.app.deps import get_db
from backend.app.errors import Conflict, Forbidden, NotFound
from backend.app.models import Course, Enrollment, EnrollmentRequest, Quiz, utcnow

router = APIRouter(prefix="/api", tags=["learning"])
DB = Annotated[Session, Depends(get_db)]


@router.get("/students/{student_id}/enrollments", response_model=list[schemas.EnrollmentOut])
def list_enrollments(student: StudentDep, db: DB, status: schemas.EnrollmentStatus | None = Query(None)):
    stmt = select(Enrollment).where(Enrollment.student_id == student.id)
    if status:
        stmt = stmt.where(Enrollment.status == status)
    return [services.enrollment_out(e) for e in db.scalars(stmt.order_by(Enrollment.enrolled_at.desc()))]


@router.post("/students/{student_id}/enrollments", response_model=schemas.EnrollmentOut, status_code=201)
def create_enrollment(student: StudentDep, data: schemas.EnrollmentCreate, principal: PrincipalDep, db: DB):
    """Unlocked courses can be joined directly; a LOCKED course needs an administrator's approval (enrolment request)."""
    course = services.get_or_404(db, Course, data.course_id)
    if not principal.is_admin and (course.is_locked or not course.is_active):
        raise Forbidden("This course is locked: send an access request for an administrator to approve.",
                        code="approval_required")
    return services.enrollment_out(services.enroll(db, student, course))


@router.get("/students/{student_id}/enrollment-requests", response_model=list[schemas.EnrollmentRequestOut])
def list_enrollment_requests(student: StudentDep, db: DB, status: schemas.RequestStatus | None = Query(None)):
    stmt = select(EnrollmentRequest).where(EnrollmentRequest.student_id == student.id)
    if status:
        stmt = stmt.where(EnrollmentRequest.status == status)
    return [services.request_out(r) for r in db.scalars(stmt.order_by(EnrollmentRequest.requested_at.desc()))]


@router.post("/students/{student_id}/enrollment-requests", response_model=schemas.EnrollmentRequestOut,
             status_code=201)
def create_enrollment_request(student: StudentDep, data: schemas.EnrollmentRequestCreate, db: DB):
    course = services.get_or_404(db, Course, data.course_id)
    return services.request_out(services.request_enrollment(db, student, course))


@router.delete("/students/{student_id}/enrollment-requests/{request_id}", status_code=204)
def cancel_enrollment_request(student: StudentDep, request_id: int, db: DB):
    """Withdraw a request that is still pending."""
    request = db.get(EnrollmentRequest, request_id)
    if request is None or request.student_id != student.id:
        raise NotFound(f"Request {request_id} not found")
    if request.status != "pending":
        raise Conflict(f"This request was already {request.status}", code="request_not_pending")
    request.status = "cancelled"
    request.decided_at = utcnow()
    db.commit()
    return Response(status_code=204)


@router.get("/enrollments/{enrollment_id}", response_model=schemas.EnrollmentOut)
def get_enrollment(enrollment: EnrollmentDep):
    return services.enrollment_out(enrollment)


@router.patch("/enrollments/{enrollment_id}", response_model=schemas.EnrollmentOut)
def update_enrollment(enrollment: EnrollmentDep, data: schemas.EnrollmentUpdate, db: DB):
    return services.enrollment_out(services.update_enrollment(db, enrollment, data))


@router.post("/enrollments/{enrollment_id}/lessons/{lesson_id}/complete",
             response_model=schemas.EnrollmentOut)
def complete_lesson(enrollment: EnrollmentDep, lesson_id: int, db: DB):
    return services.enrollment_out(services.complete_lesson(db, enrollment, lesson_id))


@router.get("/quizzes/{quiz_id}", response_model=schemas.QuizDetail)
def get_quiz(quiz_id: int, principal: PrincipalDep, db: DB):
    quiz = services.get_or_404(db, Quiz, quiz_id)
    if not principal.is_admin:       # students may only open quizzes of courses they are enrolled in
        enrolled = db.scalar(select(Enrollment.id).where(
            Enrollment.student_id == principal.student_id, Enrollment.course_id == quiz.course_id,
            Enrollment.status.in_(["active", "completed"])))
        if enrolled is None:
            raise NotFound(f"Quiz {quiz_id} not found")
    return dict(**services.quiz_summary(quiz), course=quiz.course, questions=quiz.questions)


@router.post("/students/{student_id}/quizzes/{quiz_id}/attempts",
             response_model=schemas.QuizResult, status_code=201)
def submit_quiz(student: StudentDep, quiz_id: int, data: schemas.QuizSubmission, db: DB, request: Request):
    student_id = student.id
    quiz = services.get_or_404(db, Quiz, quiz_id)
    attempt, feedback = services.submit_quiz(db, student, quiz, data)
    try:   # online update of the adaptive-difficulty bandit; must never fail the submission
        request.app.state.ml.observe_attempt(db, student_id, attempt.id)
    except Exception:
        logging.getLogger("backend.ml").exception("Bandit update failed")
    return dict(**services.attempt_out(attempt), feedback=feedback)
