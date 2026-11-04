from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.app import schemas, services
from backend.app.deps import get_db
from backend.app.models import Course

router = APIRouter(prefix="/api/courses", tags=["courses"])
DB = Annotated[Session, Depends(get_db)]


@router.get("", response_model=schemas.Page[schemas.CourseSummary])
def list_courses(db: DB, search: str | None = Query(None, max_length=100),
                 topic: str | None = Query(None, max_length=60),
                 difficulty: schemas.Difficulty | None = None,
                 content_format: schemas.ContentType | None = None,
                 limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    stmt = select(Course)
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
def get_course(course_id: int, db: DB):
    return services.course_detail(db, services.get_or_404(db, Course, course_id))
