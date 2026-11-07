"""Course catalogue (any signed-in user) and course management (administrators only)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.app import schemas, services
from backend.app.auth import AdminDep, PrincipalDep
from backend.app.deps import get_db
from backend.app.errors import Conflict, Invalid, NotFound
from backend.app.models import Course, Enrollment, Lesson, Quiz, QuizAttempt, QuizQuestion

router = APIRouter(prefix="/api/courses", tags=["courses"])
DB = Annotated[Session, Depends(get_db)]
LEVELS = {"Beginner": 1, "Intermediate": 2, "Advanced": 3}


# ------------------------------------------------------------------ admin schemas
class LessonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    duration_min: int = Field(ge=1, le=600)


class QuestionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=1, max_length=1000)
    options: list[str] = Field(min_length=2, max_length=6)
    correct_option: int = Field(ge=0)
    skill: str = Field(min_length=1, max_length=60)
    explanation: str = Field(default="", max_length=1000)

    @field_validator("options")
    @classmethod
    def _options(cls, v: list[str]) -> list[str]:
        if any(not o.strip() or len(o) > 300 for o in v):
            raise ValueError("options must be non-empty and at most 300 characters")
        return v


class QuizIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    pass_score: float = Field(default=60.0, ge=0, le=100)
    questions: list[QuestionIn] = Field(min_length=1, max_length=50)


class CourseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^[A-Za-z0-9-]{2,20}$")
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)
    topic: str = Field(min_length=1, max_length=60)
    difficulty: schemas.Difficulty
    content_format: schemas.ContentType
    duration_hours: float = Field(gt=0, le=1000)
    skills: list[str] = Field(min_length=1, max_length=20)
    prerequisite_ids: list[int] = Field(default_factory=list, max_length=10)
    lessons: list[LessonIn] = Field(min_length=1, max_length=100)
    quiz: QuizIn | None = None
    is_locked: bool = False            # new courses are open unless the administrator locks them

    @field_validator("skills")
    @classmethod
    def _skills(cls, v: list[str]) -> list[str]:
        cleaned = [s.strip() for s in v]
        if any(not s or len(s) > 60 for s in cleaned):
            raise ValueError("skills must be non-empty and at most 60 characters")
        return cleaned


class CourseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=4000)
    topic: str | None = Field(default=None, min_length=1, max_length=60)
    difficulty: schemas.Difficulty | None = None
    content_format: schemas.ContentType | None = None
    duration_hours: float | None = Field(default=None, gt=0, le=1000)
    is_active: bool | None = None      # False = hidden from the student catalogue
    is_locked: bool | None = None      # True = students need an administrator's approval


# ------------------------------------------------------------------- catalogue
def _visible(course: Course, principal, db: Session) -> bool:
    if principal.is_admin or course.is_active:
        return True
    return db.scalar(select(Enrollment.id).where(Enrollment.student_id == principal.student_id,
                                                 Enrollment.course_id == course.id)) is not None


@router.get("", response_model=schemas.Page[schemas.CourseSummary])
def list_courses(principal: PrincipalDep, db: DB, search: str | None = Query(None, max_length=100),
                 topic: str | None = Query(None, max_length=60),
                 difficulty: schemas.Difficulty | None = None,
                 content_format: schemas.ContentType | None = None,
                 include_archived: bool = False,
                 limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    stmt = select(Course)
    if not (principal.is_admin and include_archived):
        stmt = stmt.where(Course.is_active.is_(True))
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(Course.title.ilike(like), Course.description.ilike(like),
                              Course.code.ilike(like)))
    if topic:
        stmt = stmt.where(Course.topic == topic)
    if difficulty:
        stmt = stmt.where(Course.difficulty == difficulty)
    if content_format:
        stmt = stmt.where(Course.content_format == content_format)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    courses = db.scalars(stmt.order_by(Course.topic, Course.level, Course.code)
                         .limit(limit).offset(offset)).all()
    stats = services.course_stats(db, [c.id for c in courses])
    return {"items": [services.course_summary(c, stats) for c in courses],
            "total": total, "limit": limit, "offset": offset}


@router.get("/{course_id}", response_model=schemas.CourseDetail)
def get_course(course_id: int, principal: PrincipalDep, db: DB):
    course = services.get_or_404(db, Course, course_id)
    if not _visible(course, principal, db):
        raise NotFound(f"Course {course_id} not found")
    return services.course_detail(db, course)


# ------------------------------------------------------------ administration
def _prerequisites(db: Session, ids: list[int], own_id: int | None = None) -> list[Course]:
    found = list(db.scalars(select(Course).where(Course.id.in_(set(ids))))) if ids else []
    missing = set(ids) - {c.id for c in found}
    if missing:
        raise Invalid(f"Unknown prerequisite course ids: {sorted(missing)}")
    if own_id in ids:
        raise Invalid("A course cannot be its own prerequisite")
    return found


@router.post("", response_model=schemas.CourseDetail, status_code=201)
def create_course(_admin: AdminDep, data: CourseCreate, db: DB):
    code = data.code.upper()
    if db.scalar(select(Course.id).where(Course.code == code)) is not None:
        raise Conflict(f"Course code {code} already exists", code="course_code_taken")
    if data.quiz:
        for i, q in enumerate(data.quiz.questions, 1):
            if q.correct_option >= len(q.options):
                raise Invalid(f"Question {i}: correct_option must index one of its options")
    course = Course(code=code, title=data.title.strip(), description=data.description.strip(), topic=data.topic.strip(),
                    difficulty=data.difficulty, level=LEVELS[data.difficulty], content_format=data.content_format,
                    duration_hours=data.duration_hours, skills=data.skills, is_active=True, is_locked=data.is_locked,
                    prerequisites=_prerequisites(db, data.prerequisite_ids))
    course.lessons = [Lesson(position=i, title=l.title.strip(), duration_min=l.duration_min)
                      for i, l in enumerate(data.lessons, 1)]
    if data.quiz:
        course.quizzes = [Quiz(title=data.quiz.title.strip(), difficulty=data.difficulty,
                               pass_score=data.quiz.pass_score,
                               questions=[QuizQuestion(position=i, prompt=q.prompt, options=q.options,
                                                       correct_option=q.correct_option, skill=q.skill,
                                                       explanation=q.explanation)
                                          for i, q in enumerate(data.quiz.questions, 1)])]
    db.add(course)
    db.commit()
    db.refresh(course)
    return services.course_detail(db, course)


@router.patch("/{course_id}", response_model=schemas.CourseDetail)
def update_course(course_id: int, _admin: AdminDep, data: CourseUpdate, db: DB):
    """Edit metadata or archive/restore (``is_active``). Archiving keeps every enrolment and attempt."""
    course = services.get_or_404(db, Course, course_id)
    changes = data.model_dump(exclude_unset=True)
    if any(v is None for v in changes.values()):
        raise Invalid("Fields cannot be null")
    if "difficulty" in changes:
        course.level = LEVELS[changes["difficulty"]]
    for key, value in changes.items():
        setattr(course, key, value.strip() if isinstance(value, str) else value)
    db.commit()
    return services.course_detail(db, course)


@router.delete("/{course_id}", status_code=204)
def delete_course(course_id: int, _admin: AdminDep, db: DB):
    """Only a course nobody has used can be deleted; otherwise archive it (PATCH ``is_active=false``)."""
    course = services.get_or_404(db, Course, course_id)
    used = db.scalar(select(func.count(Enrollment.id)).where(Enrollment.course_id == course_id)) or \
        db.scalar(select(func.count(QuizAttempt.id)).join(Quiz).where(Quiz.course_id == course_id))
    if used:
        raise Conflict("This course has enrolments or quiz attempts; archive it instead of deleting it",
                       code="course_in_use")
    db.delete(course)
    db.commit()
    return Response(status_code=204)
