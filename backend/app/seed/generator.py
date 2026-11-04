"""Seed the database: real catalogue + 100 students from ``sample_data.csv``
+ a **synthetic**, seeded learning history for each of them.

What is real and what is synthetic
----------------------------------
* Course catalogue, lessons, quiz questions: hand-written content (catalog.py).
* Student profiles (id, age, learning style, preferred content, daily study
  minutes): taken from the original ``sample_data.csv``. Names and e-mail
  addresses are generated placeholders (``@example.edu``).
* Enrolments, lesson completions, quiz attempts, ratings, activity logs:
  SYNTHETIC, generated here with a fixed random seed, constrained so they agree
  with each student's original row:
    - number of completed courses       == CompletedCourses
    - lesson progress in active courses ~= Progress
    - mean quiz score                   ~= AverageScore
    - daily study time scales with         SessionTime
  Every seeded student has ``is_synthetic = True``.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import (ActivityLog, Course, Enrollment, Lesson, LessonCompletion,
                                Quiz, QuizAttempt, QuizQuestion, Student)
from backend.app.seed.catalog import COURSES, LEVELS
from ml.config import SAMPLE_DATA_PATH

HISTORY_DAYS = 84   # 12 weeks of history
LESSONS_PER_COURSE = 5

FIRST_NAMES = ["Aarav", "Maya", "Liam", "Sofia", "Noah", "Amara", "Ethan", "Zara", "Lucas", "Priya",
               "Mateo", "Hana", "Omar", "Chloe", "Kenji", "Elena", "Diego", "Aisha", "Leo", "Nina",
               "Ravi", "Grace", "Yusuf", "Ivy", "Samuel", "Leila", "Arjun", "Mia", "Tomas", "Fatima",
               "Daniel", "Sara", "Kofi", "Emma", "Hiro", "Lucia", "Ibrahim", "Ana", "Felix", "Meera"]
LAST_NAMES = ["Sharma", "Johnson", "Okafor", "Garcia", "Chen", "Müller", "Silva", "Khan", "Rossi",
              "Nakamura", "Patel", "Brown", "Haddad", "Kowalski", "Mensah", "Novak", "Reyes", "Ali",
              "Larsen", "Kim", "Dubois", "Ivanova", "Santos", "Nair", "Walker", "Costa", "Yilmaz",
              "Andersen", "Moreau", "Singh", "Lopez", "Tanaka", "Osei", "Fischer", "Rahman", "Ortiz",
              "Murphy", "Park", "Hughes", "Reddy"]


# --------------------------------------------------------------------- catalogue
def seed_catalog(db: Session) -> dict[str, Course]:
    courses: dict[str, Course] = {}
    for spec in COURSES:
        course = Course(code=spec["code"], title=spec["title"], description=spec["description"],
                        topic=spec["topic"], difficulty=spec["difficulty"],
                        level=LEVELS[spec["difficulty"]], content_format=spec["format"],
                        duration_hours=spec["hours"], skills=spec["skills"])
        minutes = round(spec["hours"] * 60 / len(spec["lessons"]))
        course.lessons = [Lesson(position=i + 1, title=t, duration_min=minutes)
                          for i, t in enumerate(spec["lessons"])]
        quiz = Quiz(title=f"{spec['title']} – Knowledge Check", difficulty=spec["difficulty"])
        quiz.questions = [QuizQuestion(position=i + 1, skill=q[0], prompt=q[1], options=q[2],
                                       correct_option=q[3], explanation=q[4])
                          for i, q in enumerate(spec["questions"])]
        course.quizzes = [quiz]
        courses[spec["code"]] = course
        db.add(course)
    for spec in COURSES:
        courses[spec["code"]].prerequisites = [courses[c] for c in spec["prereqs"]]
    db.flush()
    return courses


# ---------------------------------------------------------------------- students
def _at(day: date, rng: np.random.Generator) -> datetime:
    return datetime.combine(day, time(int(rng.integers(7, 22)), int(rng.integers(0, 60))))


def _pick_course(rng, candidates: list[Course], student_row, favourite_topics) -> Course:
    weights = np.array([
        1.0
        + 1.5 * (c.topic in favourite_topics)
        + 1.0 * (c.content_format == student_row.PreferredContent)
        + 0.5 * (c.level == 1)
        for c in candidates])
    return candidates[int(rng.choice(len(candidates), p=weights / weights.sum()))]


def _available(courses, done_ids, taken_ids):
    return [c for c in courses
            if c.id not in taken_ids and all(p.id in done_ids for p in c.prerequisites)]


def seed_student(db: Session, row, courses: list[Course], today: date, random_state: int) -> Student:
    rng = np.random.default_rng(random_state * 1000 + int(row.StudentID))
    sid = int(row.StudentID)
    first, last = FIRST_NAMES[int(rng.integers(len(FIRST_NAMES)))], LAST_NAMES[int(rng.integers(len(LAST_NAMES)))]
    student = Student(id=sid, name=f"{first} {last}",
                      email=f"{first.lower()}.{last.lower()}.{sid}@example.edu".replace("ü", "u"),
                      age=int(row.Age), learning_style=row.LearningStyle,
                      preferred_content=row.PreferredContent,
                      daily_goal_minutes=round(float(row.SessionTime), 1), is_synthetic=True,
                      created_at=_at(today - timedelta(days=HISTORY_DAYS + 7), rng))
    db.add(student)

    topics = sorted({c.topic for c in courses})
    favourite_topics = set(rng.choice(topics, size=2, replace=False))
    start = today - timedelta(days=HISTORY_DAYS)
    done_ids: set[int] = set()
    taken_ids: set[int] = set()
    enrollments: list[Enrollment] = []
    quiz_plan: list[tuple[Course, date]] = []
    activity: list[ActivityLog] = []

    # Completed courses, one after another across the first ~10 weeks.
    n_completed = int(row.CompletedCourses)
    span = (HISTORY_DAYS - 14) / max(n_completed, 1)
    for k in range(n_completed):
        candidates = _available(courses, done_ids, taken_ids)
        if not candidates:
            break
        course = _pick_course(rng, candidates, row, favourite_topics)
        begin = start + timedelta(days=int(k * span))
        finish = begin + timedelta(days=max(2, int(span) - int(rng.integers(0, 3))))
        enrollment = Enrollment(course=course, status="completed",
                                enrolled_at=_at(begin, rng), completed_at=_at(finish, rng))
        match = course.content_format == row.PreferredContent
        if rng.random() < 0.75:
            rating = 3.1 + 0.9 * match + 0.6 * (course.topic in favourite_topics) + rng.normal(0, 0.7)
            enrollment.rating = int(np.clip(round(rating), 1, 5))
        for i, lesson in enumerate(course.lessons):
            day = begin + timedelta(days=int((finish - begin).days * (i + 1) / len(course.lessons)))
            enrollment.completions.append(LessonCompletion(lesson_id=lesson.id, completed_at=_at(day, rng)))
            activity.append(ActivityLog(course_id=course.id, activity_date=day, kind="lesson",
                                        minutes=round(lesson.duration_min * rng.uniform(0.7, 1.3), 1)))
        quiz_plan.append((course, finish))
        enrollments.append(enrollment)
        done_ids.add(course.id)
        taken_ids.add(course.id)

    # Occasionally a dropped course.
    if rng.random() < 0.15:
        candidates = _available(courses, done_ids, taken_ids)
        if candidates:
            course = _pick_course(rng, candidates, row, favourite_topics)
            day = start + timedelta(days=int(rng.integers(5, HISTORY_DAYS - 20)))
            enrollment = Enrollment(course=course, status="dropped", enrolled_at=_at(day, rng))
            enrollment.completions.append(LessonCompletion(lesson_id=course.lessons[0].id,
                                                           completed_at=_at(day + timedelta(days=1), rng)))
            activity.append(ActivityLog(course_id=course.id, activity_date=day + timedelta(days=1),
                                        kind="lesson", minutes=float(course.lessons[0].duration_min)))
            enrollments.append(enrollment)
            taken_ids.add(course.id)

    # 1–2 active courses whose lesson progress follows the original Progress value.
    for _ in range(1 + int(rng.random() < 0.5)):
        candidates = _available(courses, done_ids, taken_ids)
        if not candidates:
            break
        course = _pick_course(rng, candidates, row, favourite_topics)
        begin = today - timedelta(days=int(rng.integers(8, 21)))
        n_done = int(np.clip(round(float(row.Progress) * LESSONS_PER_COURSE + rng.normal(0, 0.4)),
                             0, LESSONS_PER_COURSE - 1))
        enrollment = Enrollment(course=course, status="active", enrolled_at=_at(begin, rng))
        for i in range(n_done):
            day = begin + timedelta(days=int((today - begin).days * (i + 1) / (n_done + 1)))
            lesson = course.lessons[i]
            enrollment.completions.append(LessonCompletion(lesson_id=lesson.id, completed_at=_at(day, rng)))
            activity.append(ActivityLog(course_id=course.id, activity_date=day, kind="lesson",
                                        minutes=round(lesson.duration_min * rng.uniform(0.7, 1.3), 1)))
        if n_done >= 3:
            quiz_plan.append((course, today - timedelta(days=int(rng.integers(0, 3)))))
        enrollments.append(enrollment)
        taken_ids.add(course.id)

    student.enrollments = enrollments

    # Quiz scores: difficulty effect + personal learning trend, then re-centred
    # so the student's mean equals AverageScore from sample_data.csv.
    if quiz_plan:
        trend = rng.normal(0.08, 0.06)    # points per day
        raw = np.array([rng.normal(0, 6) - 4 * (c.level - 2) + trend * (d - start).days
                        for c, d in quiz_plan])
        scores = np.clip(raw - raw.mean() + float(row.AverageScore), 0, 100)
        for (course, day), score in zip(quiz_plan, scores):
            minutes = round(float(rng.uniform(6, 18)), 1)
            student.quiz_attempts.append(QuizAttempt(
                quiz=course.quizzes[0], score=round(float(score), 1), time_taken_min=minutes,
                attempted_at=_at(day, rng)))
            activity.append(ActivityLog(course_id=course.id, activity_date=day, kind="quiz", minutes=minutes))

    # Extra self-study sessions; frequency and length scale with SessionTime.
    intensity = float(row.SessionTime) / 120.0
    for offset in range(HISTORY_DAYS):
        if rng.random() < 0.15 + 0.35 * intensity:
            day = start + timedelta(days=offset)
            activity.append(ActivityLog(activity_date=day, kind="study",
                                        minutes=round(max(5.0, rng.normal(0.4, 0.1) * float(row.SessionTime)), 1)))
    student.activity = activity
    return student


def seed_database(db: Session, *, random_state: int = 42, today: date | None = None,
                  sample_path=SAMPLE_DATA_PATH) -> dict:
    """Populate an empty database. Returns row counts."""
    if db.scalar(select(Course.id).limit(1)) is not None:
        raise RuntimeError("Database already contains data; reset it first.")
    today = today or date.today()
    catalog = list(seed_catalog(db).values())
    students = pd.read_csv(sample_path)
    for row in students.itertuples(index=False):
        seed_student(db, row, catalog, today, random_state)
    db.commit()
    return database_counts(db)


def database_counts(db: Session) -> dict:
    from sqlalchemy import func
    tables = {"students": Student, "courses": Course, "lessons": Lesson, "quizzes": Quiz,
              "quiz_questions": QuizQuestion, "enrollments": Enrollment,
              "lesson_completions": LessonCompletion, "quiz_attempts": QuizAttempt,
              "activity_logs": ActivityLog}
    return {name: db.scalar(select(func.count()).select_from(model)) for name, model in tables.items()}
