"""Enrolments, lesson progress and quizzes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app import schemas, services
from backend.app.deps import get_db
from backend.app.models import Course, Enrollment, Quiz, Student

router = APIRouter(prefix="/api", tags=["learning"])
DB = Annotated[Session, Depends(get_db)]


@router.get("/students/{student_id}/enrollments", response_model=list[schemas.EnrollmentOut])
def list_enrollments(student_id: int, db: DB, status: schemas.EnrollmentStatus | None = Query(None)):
    services.get_or_404(db, Student, student_id)
    stmt = select(Enrollment).where(Enrollment.student_id == student_id)
    if status:
        stmt = stmt.where(Enrollment.status == status)
    return [services.enrollment_out(e) for e in db.scalars(stmt.order_by(Enrollment.enrolled_at.desc()))]


@router.post("/students/{student_id}/enrollments", response_model=schemas.EnrollmentOut, status_code=201)
def create_enrollment(student_id: int, data: schemas.EnrollmentCreate, db: DB):
    student = services.get_or_404(db, Student, student_id)
    course = services.get_or_404(db, Course, data.course_id)
    return services.enrollment_out(services.enroll(db, student, course))


@router.get("/enrollments/{enrollment_id}", response_model=schemas.EnrollmentOut)
def get_enrollment(enrollment_id: int, db: DB):
    return services.enrollment_out(services.get_or_404(db, Enrollment, enrollment_id))


@router.patch("/enrollments/{enrollment_id}", response_model=schemas.EnrollmentOut)
def update_enrollment(enrollment_id: int, data: schemas.EnrollmentUpdate, db: DB):
    enrollment = services.get_or_404(db, Enrollment, enrollment_id)
    return services.enrollment_out(services.update_enrollment(db, enrollment, data))


@router.post("/enrollments/{enrollment_id}/lessons/{lesson_id}/complete",
             response_model=schemas.EnrollmentOut)
def complete_lesson(enrollment_id: int, lesson_id: int, db: DB):
    enrollment = services.get_or_404(db, Enrollment, enrollment_id)
    return services.enrollment_out(services.complete_lesson(db, enrollment, lesson_id))


@router.get("/quizzes/{quiz_id}", response_model=schemas.QuizDetail)
def get_quiz(quiz_id: int, db: DB):
    quiz = services.get_or_404(db, Quiz, quiz_id)
    return dict(**services.quiz_summary(quiz), course=quiz.course, questions=quiz.questions)


@router.post("/students/{student_id}/quizzes/{quiz_id}/attempts",
             response_model=schemas.QuizResult, status_code=201)
def submit_quiz(student_id: int, quiz_id: int, data: schemas.QuizSubmission, db: DB):
    student = services.get_or_404(db, Student, student_id)
    quiz = services.get_or_404(db, Quiz, quiz_id)
    attempt, feedback = services.submit_quiz(db, student, quiz, data)
    return dict(**services.attempt_out(attempt), feedback=feedback)
