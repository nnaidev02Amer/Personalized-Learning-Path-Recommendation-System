"""Database tables (SQLAlchemy 2.0 ORM)."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (JSON, Boolean, CheckConstraint, Column, Date, DateTime, Float,
                        ForeignKey, Index, Integer, String, Table, Text, UniqueConstraint)
from sqlalchemy import text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


course_prerequisites = Table(
    "course_prerequisites",
    Base.metadata,
    Column("course_id", ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
    Column("prerequisite_id", ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
)


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    age: Mapped[int] = mapped_column(Integer)
    # Self-reported / labelled style; the ML-predicted style is added in Phase 5.
    learning_style: Mapped[str | None] = mapped_column(String(30))
    preferred_content: Mapped[str] = mapped_column(String(30))
    daily_goal_minutes: Mapped[float] = mapped_column(Float)   # SessionTime in sample_data.csv
    # True when the profile's history was produced by the synthetic seed generator.
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    enrollments: Mapped[list[Enrollment]] = relationship(
        back_populates="student", cascade="all, delete-orphan")
    quiz_attempts: Mapped[list[QuizAttempt]] = relationship(
        back_populates="student", cascade="all, delete-orphan")
    activity: Mapped[list[ActivityLog]] = relationship(
        back_populates="student", cascade="all, delete-orphan")


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    topic: Mapped[str] = mapped_column(String(60), index=True)
    difficulty: Mapped[str] = mapped_column(String(20))      # Beginner / Intermediate / Advanced
    level: Mapped[int] = mapped_column(Integer)              # 1 / 2 / 3 (sortable difficulty)
    content_format: Mapped[str] = mapped_column(String(30))  # Videos / Articles / Podcasts / Quizzes
    duration_hours: Mapped[float] = mapped_column(Float)
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Archived courses disappear from the student catalogue but keep every enrolment and attempt.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    # Locked courses need an administrator's approval (enrolment request); unlocked ones can be joined directly.
    is_locked: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")

    prerequisites: Mapped[list[Course]] = relationship(
        secondary=course_prerequisites,
        primaryjoin=id == course_prerequisites.c.course_id,
        secondaryjoin=id == course_prerequisites.c.prerequisite_id,
        lazy="selectin")
    lessons: Mapped[list[Lesson]] = relationship(
        back_populates="course", order_by="Lesson.position",
        cascade="all, delete-orphan", lazy="selectin")
    quizzes: Mapped[list[Quiz]] = relationship(
        back_populates="course", cascade="all, delete-orphan")
    enrollments: Mapped[list[Enrollment]] = relationship(back_populates="course")


class Lesson(Base):
    __tablename__ = "lessons"
    __table_args__ = (UniqueConstraint("course_id", "position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    duration_min: Mapped[int] = mapped_column(Integer)

    course: Mapped[Course] = relationship(back_populates="lessons")


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    difficulty: Mapped[str] = mapped_column(String(20))
    pass_score: Mapped[float] = mapped_column(Float, default=60.0)

    course: Mapped[Course] = relationship(back_populates="quizzes")
    questions: Mapped[list[QuizQuestion]] = relationship(
        back_populates="quiz", order_by="QuizQuestion.position",
        cascade="all, delete-orphan", lazy="selectin")


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    prompt: Mapped[str] = mapped_column(Text)
    options: Mapped[list[str]] = mapped_column(JSON)
    correct_option: Mapped[int] = mapped_column(Integer)
    skill: Mapped[str] = mapped_column(String(60))
    explanation: Mapped[str] = mapped_column(Text, default="")

    quiz: Mapped[Quiz] = relationship(back_populates="questions")


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("student_id", "course_id"),
        CheckConstraint("rating IS NULL OR (rating BETWEEN 1 AND 5)", name="rating_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="active")   # active / completed / dropped
    rating: Mapped[int | None] = mapped_column(Integer)
    enrolled_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    student: Mapped[Student] = relationship(back_populates="enrollments")
    course: Mapped[Course] = relationship(back_populates="enrollments", lazy="joined")
    completions: Mapped[list[LessonCompletion]] = relationship(
        back_populates="enrollment", cascade="all, delete-orphan", lazy="selectin")

    @property
    def progress(self) -> float:
        total = len(self.course.lessons)
        return round(len(self.completions) / total, 4) if total else 0.0


class LessonCompletion(Base):
    __tablename__ = "lesson_completions"
    __table_args__ = (UniqueConstraint("enrollment_id", "lesson_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    enrollment_id: Mapped[int] = mapped_column(
        ForeignKey("enrollments.id", ondelete="CASCADE"), index=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"))
    completed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    enrollment: Mapped[Enrollment] = relationship(back_populates="completions")


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"), index=True)
    score: Mapped[float] = mapped_column(Float)                 # 0-100
    correct: Mapped[int | None] = mapped_column(Integer)
    total: Mapped[int | None] = mapped_column(Integer)
    answers: Mapped[list[int] | None] = mapped_column(JSON)     # None for seeded history
    time_taken_min: Mapped[float | None] = mapped_column(Float)
    attempted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    student: Mapped[Student] = relationship(back_populates="quiz_attempts")
    quiz: Mapped[Quiz] = relationship(lazy="joined")


class ActivityLog(Base):
    """One learning session (lesson study, quiz, or manually logged time)."""

    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id", ondelete="SET NULL"))
    activity_date: Mapped[date] = mapped_column(Date, index=True)
    minutes: Mapped[float] = mapped_column(Float)
    kind: Mapped[str] = mapped_column(String(20))   # lesson / quiz / study

    student: Mapped[Student] = relationship(back_populates="activity")


class User(Base):
    """A login account. ``student_id`` links a student account to its (single) learner profile."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'student')", name="user_role"),
        # Exactly one administrator can ever exist: a partial unique index over the admin rows only.
        Index("uq_single_admin", "role", unique=True, sqlite_where=text("role = 'admin'")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="student")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    # One login per learner profile; deleting the student deletes the login with it.
    student_id: Mapped[int | None] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), unique=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)

    student: Mapped[Student | None] = relationship()
    sessions: Mapped[list[AuthSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True)


class AuthSession(Base):
    """A server-side session. Only the SHA-256 of the cookie token is stored."""

    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)

    user: Mapped[User] = relationship(back_populates="sessions")


class RecommendationHistory(Base):
    """What the recommender showed a student (a new row only when the list changed)."""

    __tablename__ = "recommendation_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id", ondelete="SET NULL"))
    method: Mapped[str] = mapped_column(String(30))
    items: Mapped[list] = mapped_column(JSON)
    model_trained_at: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class EnrollmentRequest(Base):
    """A student's request to join a course. Only an approval creates the real :class:`Enrollment`,
    so pending/rejected requests never reach the learning data or the ML models."""

    __tablename__ = "enrollment_requests"
    __table_args__ = (CheckConstraint("status IN ('pending', 'approved', 'rejected', 'cancelled')",
                                      name="request_status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    note: Mapped[str | None] = mapped_column(String(500))          # admin's reason when rejecting
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    student: Mapped[Student] = relationship(lazy="joined")
    course: Mapped[Course] = relationship(lazy="joined")
