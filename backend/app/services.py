"""Business logic shared by the routers: lookups, rules, serialisation, analytics."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app import schemas
from backend.app.errors import Conflict, Invalid, NotFound
from backend.app.models import (ActivityLog, Course, Enrollment, EnrollmentRequest, Lesson, LessonCompletion, Quiz,
                                QuizAttempt, Student, utcnow)


# ------------------------------------------------------------------- lookups
def get_or_404(db: Session, model, obj_id: int):
    obj = db.get(model, obj_id)
    if obj is None:
        raise NotFound(f"{model.__name__} {obj_id} not found")
    return obj


# ------------------------------------------------------------- serialisation
def course_stats(db: Session, course_ids: list[int] | None = None) -> dict[int, tuple[int, float | None]]:
    """course_id -> (enrolled_count, average_rating)."""
    stmt = (select(Enrollment.course_id, func.count(Enrollment.id), func.avg(Enrollment.rating))
            .group_by(Enrollment.course_id))
    if course_ids is not None:
        stmt = stmt.where(Enrollment.course_id.in_(course_ids))
    return {cid: (n, round(avg, 2) if avg is not None else None) for cid, n, avg in db.execute(stmt)}


def course_summary(course: Course, stats: dict) -> dict:
    enrolled, rating = stats.get(course.id, (0, None))
    return dict(id=course.id, code=course.code, title=course.title, topic=course.topic,
                difficulty=course.difficulty, content_format=course.content_format,
                level=course.level, duration_hours=course.duration_hours, skills=course.skills,
                lesson_count=len(course.lessons),
                prerequisite_codes=[p.code for p in course.prerequisites],
                enrolled_count=enrolled, average_rating=rating, is_active=course.is_active,
                is_locked=course.is_locked)


def quiz_summary(quiz: Quiz) -> dict:
    return dict(id=quiz.id, title=quiz.title, difficulty=quiz.difficulty,
                pass_score=quiz.pass_score, question_count=len(quiz.questions))


def course_detail(db: Session, course: Course) -> dict:
    return dict(**course_summary(course, course_stats(db, [course.id])),
                description=course.description, lessons=course.lessons,
                prerequisites=course.prerequisites,
                quizzes=[quiz_summary(q) for q in course.quizzes])


def enrollment_out(e: Enrollment) -> dict:
    done = {c.lesson_id for c in e.completions}
    lessons = e.course.lessons
    next_lesson = next((l for l in lessons if l.id not in done), None) if e.status == "active" else None
    return dict(id=e.id, student_id=e.student_id, course=e.course, status=e.status,
                progress=e.progress, completed_lessons=len(done), total_lessons=len(lessons),
                completed_lesson_ids=sorted(done), next_lesson=next_lesson, rating=e.rating,
                enrolled_at=e.enrolled_at, completed_at=e.completed_at)


def attempt_out(a: QuizAttempt) -> dict:
    return dict(id=a.id, quiz_id=a.quiz_id, quiz_title=a.quiz.title, course_id=a.quiz.course_id,
                course_title=a.quiz.course.title, score=a.score, correct=a.correct, total=a.total,
                passed=a.score >= a.quiz.pass_score, time_taken_min=a.time_taken_min,
                attempted_at=a.attempted_at)


# ------------------------------------------------------------ enrolment rules
def enroll(db: Session, student: Student, course: Course) -> Enrollment:
    if not course.is_active:
        raise Conflict(f"{course.code} is archived and not open for enrolment", code="course_archived")
    existing = db.scalar(select(Enrollment).where(Enrollment.student_id == student.id,
                                                  Enrollment.course_id == course.id))
    if existing is not None:
        if existing.status == "dropped":
            existing.status = "active"
            db.commit()
            return existing
        raise Conflict(f"Student is already enrolled in {course.code} ({existing.status})",
                       code="already_enrolled")

    completed = set(db.scalars(select(Enrollment.course_id).where(
        Enrollment.student_id == student.id, Enrollment.status == "completed")))
    missing = [p for p in course.prerequisites if p.id not in completed]
    if missing:
        raise Conflict(f"Complete the prerequisites for {course.code} first",
                       details=[{"id": p.id, "code": p.code, "title": p.title} for p in missing],
                       code="prerequisites_not_met")

    enrollment = Enrollment(student_id=student.id, course_id=course.id, status="active")
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    return enrollment


def _check_prerequisites(db: Session, student: Student, course: Course) -> None:
    completed = set(db.scalars(select(Enrollment.course_id).where(
        Enrollment.student_id == student.id, Enrollment.status == "completed")))
    missing = [p for p in course.prerequisites if p.id not in completed]
    if missing:
        raise Conflict(f"Complete the prerequisites for {course.code} first",
                       details=[{"id": p.id, "code": p.code, "title": p.title} for p in missing],
                       code="prerequisites_not_met")


def request_out(r: EnrollmentRequest) -> dict:
    return dict(id=r.id, student_id=r.student_id, student_name=r.student.name, student_email=r.student.email,
                course=r.course, status=r.status, note=r.note, requested_at=r.requested_at,
                decided_at=r.decided_at)


def request_enrollment(db: Session, student: Student, course: Course) -> EnrollmentRequest:
    """A student asks to join a course; nothing is enrolled until an administrator approves."""
    if not course.is_active:
        raise Conflict(f"{course.code} is archived and not open for enrolment", code="course_archived")
    if not course.is_locked:
        raise Conflict(f"{course.code} is open: enrol directly, no request is needed", code="course_unlocked")
    existing = db.scalar(select(Enrollment).where(Enrollment.student_id == student.id,
                                                  Enrollment.course_id == course.id))
    if existing is not None and existing.status != "dropped":
        raise Conflict(f"You are already enrolled in {course.code}", code="already_enrolled")
    if db.scalar(select(EnrollmentRequest.id).where(
            EnrollmentRequest.student_id == student.id, EnrollmentRequest.course_id == course.id,
            EnrollmentRequest.status == "pending")):
        raise Conflict(f"You already have a pending request for {course.code}", code="request_pending")
    _check_prerequisites(db, student, course)
    request = EnrollmentRequest(student_id=student.id, course_id=course.id, status="pending")
    db.add(request)
    db.commit()
    db.refresh(request)
    return request


def decide_request(db: Session, request: EnrollmentRequest, approve: bool, admin_user_id: int,
                   note: str | None = None) -> EnrollmentRequest:
    if request.status != "pending":
        raise Conflict(f"This request was already {request.status}", code="request_not_pending")
    if approve:
        enroll(db, request.student, request.course)       # re-checks archive/prerequisites; commits
    request.status = "approved" if approve else "rejected"
    request.note = (note or "").strip() or None
    request.decided_at, request.decided_by = utcnow(), admin_user_id
    db.commit()
    return request


def update_enrollment(db: Session, e: Enrollment, data: schemas.EnrollmentUpdate) -> Enrollment:
    if data.status is not None:
        if e.status == "completed":
            raise Conflict("A completed course cannot change status", code="invalid_status_change")
        e.status = data.status
    if data.rating is not None:
        if e.status != "completed":
            raise Conflict("Only completed courses can be rated", code="not_completed")
        e.rating = data.rating
    db.commit()
    return e


def complete_lesson(db: Session, e: Enrollment, lesson_id: int) -> Enrollment:
    lesson = db.get(Lesson, lesson_id)
    if lesson is None or lesson.course_id != e.course_id:
        raise NotFound(f"Lesson {lesson_id} is not part of course {e.course.code}")
    if any(c.lesson_id == lesson_id for c in e.completions):
        return e                                        # idempotent
    if e.status != "active":
        raise Conflict(f"Enrollment is {e.status}; only active courses can progress",
                       code="enrollment_not_active")

    e.completions.append(LessonCompletion(lesson_id=lesson_id))
    db.add(ActivityLog(student_id=e.student_id, course_id=e.course_id, activity_date=date.today(),
                       minutes=float(lesson.duration_min), kind="lesson"))
    if len(e.completions) == len(e.course.lessons):
        e.status = "completed"
        e.completed_at = utcnow()
    db.commit()
    return e


def submit_quiz(db: Session, student: Student, quiz: Quiz,
                data: schemas.QuizSubmission) -> tuple[QuizAttempt, list[dict]]:
    enrolled = db.scalar(select(Enrollment).where(
        Enrollment.student_id == student.id, Enrollment.course_id == quiz.course_id,
        Enrollment.status.in_(["active", "completed"])))
    if enrolled is None:
        raise Conflict(f"Enroll in {quiz.course.code} before taking its quiz", code="not_enrolled")

    questions = quiz.questions
    if len(data.answers) != len(questions):
        raise Invalid(f"Expected {len(questions)} answers, got {len(data.answers)}")
    feedback, correct = [], 0
    for q, answer in zip(questions, data.answers):
        if not 0 <= answer < len(q.options):
            raise Invalid(f"Answer for question {q.position} must be between 0 and {len(q.options) - 1}")
        ok = answer == q.correct_option
        correct += ok
        feedback.append(dict(question_id=q.id, skill=q.skill, selected_option=answer,
                             correct_option=q.correct_option, is_correct=ok, explanation=q.explanation))

    attempt = QuizAttempt(student_id=student.id, quiz_id=quiz.id,
                          score=round(100 * correct / len(questions), 1), correct=correct,
                          total=len(questions), answers=data.answers, time_taken_min=data.time_taken_min)
    db.add(attempt)
    if data.time_taken_min:
        db.add(ActivityLog(student_id=student.id, course_id=quiz.course_id, activity_date=date.today(),
                           minutes=data.time_taken_min, kind="quiz"))
    db.commit()
    db.refresh(attempt)
    return attempt, feedback


# ----------------------------------------------------------------- analytics
def _streak(days: set[date], today: date) -> int:
    day = today if today in days else today - timedelta(days=1)
    streak = 0
    while day in days:
        streak += 1
        day -= timedelta(days=1)
    return streak


def student_summary(db: Session, student: Student) -> dict:
    today = date.today()
    by_status = defaultdict(int)
    lessons_done = lessons_pending = 0
    for e in student.enrollments:
        by_status[e.status] += 1
        lessons_done += len(e.completions)
        if e.status == "active":
            lessons_pending += len(e.course.lessons) - len(e.completions)
    scores = [a.score for a in student.quiz_attempts]
    days = {a.activity_date for a in student.activity}
    return dict(
        student=student,
        active_courses=by_status["active"], completed_courses=by_status["completed"],
        dropped_courses=by_status["dropped"], lessons_completed=lessons_done,
        lessons_pending=lessons_pending, quizzes_taken=len(scores),
        average_quiz_score=round(float(np.mean(scores)), 1) if scores else None,
        minutes_last_7_days=round(sum(a.minutes for a in student.activity
                                      if a.activity_date > today - timedelta(days=7)), 1),
        minutes_total=round(sum(a.minutes for a in student.activity), 1),
        daily_goal_minutes=student.daily_goal_minutes,
        current_streak_days=_streak(days, today),
        last_active=max(days) if days else None)


def progress_report(db: Session, student: Student, weeks: int) -> dict:
    today = date.today()
    tracked = [e for e in student.enrollments if e.status != "dropped"]
    total_lessons = sum(len(e.course.lessons) for e in tracked)
    done_lessons = sum(len(e.completions) for e in tracked)

    # Weekly buckets (weeks start on Monday), oldest first.
    this_monday = today - timedelta(days=today.weekday())
    buckets = {this_monday - timedelta(weeks=w): dict(minutes=0.0, lessons=0, quizzes=0, days=set())
               for w in range(weeks)}
    for a in student.activity:
        week = a.activity_date - timedelta(days=a.activity_date.weekday())
        if week in buckets:
            b = buckets[week]
            b["minutes"] += a.minutes
            b["lessons"] += a.kind == "lesson"
            b["quizzes"] += a.kind == "quiz"
            b["days"].add(a.activity_date)
    weekly = [dict(week_start=w, minutes=round(b["minutes"], 1), lessons=b["lessons"],
                   quizzes=b["quizzes"], active_days=len(b["days"]))
              for w, b in sorted(buckets.items())]

    attempts = sorted(student.quiz_attempts, key=lambda a: a.attempted_at)
    points = [dict(attempted_at=a.attempted_at, score=a.score, course_title=a.quiz.course.title,
                   topic=a.quiz.course.topic) for a in attempts]

    trend = dict(attempts=len(attempts), first_half_average=None, second_half_average=None,
                 change=None, slope_per_week=None)
    if len(attempts) >= 2:
        scores = np.array([a.score for a in attempts])
        half = len(scores) // 2
        trend["first_half_average"] = round(float(scores[:half].mean()), 1)
        trend["second_half_average"] = round(float(scores[half:].mean()), 1)
        trend["change"] = round(trend["second_half_average"] - trend["first_half_average"], 1)
        days = np.array([(a.attempted_at - attempts[0].attempted_at).total_seconds() / 86400
                         for a in attempts])
        if np.ptp(days) > 0:
            trend["slope_per_week"] = round(float(np.polyfit(days, scores, 1)[0] * 7), 2)

    topic_scores = defaultdict(list)
    for a in attempts:
        topic_scores[a.quiz.course.topic].append(a.score)
    by_topic = sorted(({"topic": t, "average_score": round(float(np.mean(s)), 1), "attempts": len(s)}
                       for t, s in topic_scores.items()), key=lambda x: x["average_score"])

    return dict(student_id=student.id,
                overall_completion=round(done_lessons / total_lessons, 4) if total_lessons else 0.0,
                courses=[dict(enrollment_id=e.id, course=e.course, status=e.status, progress=e.progress)
                         for e in sorted(student.enrollments, key=lambda e: e.enrolled_at)],
                weekly_activity=weekly, quiz_scores=points, score_trend=trend,
                scores_by_topic=by_topic)
