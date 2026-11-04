from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.app import schemas
from backend.app.deps import get_db
from backend.app.models import Course
from backend.app.seed.generator import database_counts

router = APIRouter(prefix="/api", tags=["meta"])
DB = Annotated[Session, Depends(get_db)]


@router.get("/health")
def health(db: DB):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok", "counts": database_counts(db)}


@router.get("/meta", response_model=schemas.Meta)
def meta(db: DB):
    return {
        "learning_styles": list(schemas.LearningStyle.__args__),
        "content_types": list(schemas.ContentType.__args__),
        "difficulties": list(schemas.Difficulty.__args__),
        "topics": list(db.scalars(select(Course.topic).distinct().order_by(Course.topic))),
        "enrollment_statuses": list(schemas.EnrollmentStatus.__args__),
    }
