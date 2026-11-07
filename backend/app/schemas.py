"""Request/response schemas (Pydantic v2). These define and validate the API contract."""

from __future__ import annotations

from datetime import date, datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ml.schema import CONTENT_TYPES, LEARNING_STYLES

LearningStyle = Literal["Auditory", "Kinesthetic", "Reading/Writing", "Visual"]
ContentType = Literal["Articles", "Podcasts", "Quizzes", "Videos"]
Difficulty = Literal["Beginner", "Intermediate", "Advanced"]
EnrollmentStatus = Literal["active", "completed", "dropped"]
assert set(LearningStyle.__args__) == set(LEARNING_STYLES)  # keep in sync with ml.schema
assert set(ContentType.__args__) == set(CONTENT_TYPES)

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


# ------------------------------------------------------------------ students
class StudentBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
    age: int = Field(ge=10, le=100)
    learning_style: LearningStyle | None = None
    preferred_content: ContentType
    daily_goal_minutes: float = Field(default=60, gt=0, le=1440)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v

    @field_validator("email")
    @classmethod
    def _lower_email(cls, v: str) -> str:
        return v.strip().lower()


class StudentCreate(StudentBase):
    model_config = ConfigDict(extra="forbid")


class StudentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=100)
    email: str | None = Field(default=None, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
    age: int | None = Field(default=None, ge=10, le=100)
    learning_style: LearningStyle | None = None
    preferred_content: ContentType | None = None
    daily_goal_minutes: float | None = Field(default=None, gt=0, le=1440)


class StudentOut(StudentBase, ORM):
    id: int
    is_synthetic: bool
    created_at: datetime


# ------------------------------------------------------------------- courses
class CourseRef(ORM):
    id: int
    code: str
    title: str
    topic: str
    difficulty: Difficulty
    content_format: ContentType


class CourseSummary(CourseRef):
    level: int
    duration_hours: float
    skills: list[str]
    lesson_count: int
    prerequisite_codes: list[str]
    enrolled_count: int = 0
    average_rating: float | None = None
    is_active: bool = True
    is_locked: bool = True


class LessonOut(ORM):
    id: int
    position: int
    title: str
    duration_min: int


class QuizSummary(ORM):
    id: int
    title: str
    difficulty: Difficulty
    pass_score: float
    question_count: int


class CourseDetail(CourseSummary):
    description: str
    lessons: list[LessonOut]
    prerequisites: list[CourseRef]
    quizzes: list[QuizSummary]


# -------------------------------------------------------------------- quizzes
class QuestionOut(ORM):
    id: int
    position: int
    prompt: str
    options: list[str]
    skill: str


class QuizDetail(QuizSummary):
    course: CourseRef
    questions: list[QuestionOut]   # correct answers are never exposed here


class QuizSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answers: list[int] = Field(min_length=1, description="Selected option index per question, in order")
    time_taken_min: float | None = Field(default=None, ge=0, le=600)


class QuestionFeedback(BaseModel):
    question_id: int
    skill: str
    selected_option: int
    correct_option: int
    is_correct: bool
    explanation: str


class QuizAttemptOut(BaseModel):
    id: int
    quiz_id: int
    quiz_title: str
    course_id: int
    course_title: str
    score: float
    correct: int | None
    total: int | None
    passed: bool
    time_taken_min: float | None
    attempted_at: datetime


class QuizResult(QuizAttemptOut):
    feedback: list[QuestionFeedback]


# ---------------------------------------------------------------- enrollments
class EnrollmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(gt=0)


RequestStatus = Literal["pending", "approved", "rejected", "cancelled"]


class EnrollmentRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(gt=0)


class RequestDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str | None = Field(default=None, max_length=500)


class EnrollmentRequestOut(BaseModel):
    """One enrolment request; ``student_name``/``student_email`` are filled in for administrators."""
    id: int
    student_id: int
    student_name: str
    student_email: str
    course: "CourseRef"
    status: RequestStatus
    note: str | None
    requested_at: datetime
    decided_at: datetime | None


class EnrollmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["active", "dropped"] | None = None
    rating: int | None = Field(default=None, ge=1, le=5)


class EnrollmentOut(BaseModel):
    id: int
    student_id: int
    course: CourseRef
    status: EnrollmentStatus
    progress: float
    completed_lessons: int
    total_lessons: int
    completed_lesson_ids: list[int]
    next_lesson: LessonOut | None
    rating: int | None
    enrolled_at: datetime
    completed_at: datetime | None


# ------------------------------------------------------------ activity/progress
class ActivityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    minutes: float = Field(gt=0, le=600)
    activity_date: date | None = None
    course_id: int | None = Field(default=None, gt=0)

    @field_validator("activity_date")
    @classmethod
    def _not_future(cls, v: date | None) -> date | None:
        if v is not None and v > date.today():
            raise ValueError("activity_date cannot be in the future")
        return v


class ActivityOut(ORM):
    id: int
    course_id: int | None
    activity_date: date
    minutes: float
    kind: str


class StudentSummary(BaseModel):
    student: StudentOut
    active_courses: int
    completed_courses: int
    dropped_courses: int
    lessons_completed: int
    lessons_pending: int
    quizzes_taken: int
    average_quiz_score: float | None
    minutes_last_7_days: float
    minutes_total: float
    daily_goal_minutes: float
    current_streak_days: int
    last_active: date | None


class CourseProgress(BaseModel):
    enrollment_id: int
    course: CourseRef
    status: EnrollmentStatus
    progress: float


class WeeklyActivity(BaseModel):
    week_start: date
    minutes: float
    lessons: int
    quizzes: int
    active_days: int


class ScorePoint(BaseModel):
    attempted_at: datetime
    score: float
    course_title: str
    topic: str


class ScoreTrend(BaseModel):
    attempts: int
    first_half_average: float | None
    second_half_average: float | None
    change: float | None
    slope_per_week: float | None


class TopicScore(BaseModel):
    topic: str
    average_score: float
    attempts: int


class ProgressReport(BaseModel):
    student_id: int
    overall_completion: float
    courses: list[CourseProgress]
    weekly_activity: list[WeeklyActivity]
    quiz_scores: list[ScorePoint]
    score_trend: ScoreTrend
    scores_by_topic: list[TopicScore]


class Meta(BaseModel):
    learning_styles: list[str]
    content_types: list[str]
    difficulties: list[str]
    topics: list[str]
    enrollment_statuses: list[str]
