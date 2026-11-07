from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.app import schemas
from backend.app.auth import PrincipalDep, find_session
from backend.app.deps import get_db
from backend.app.models import Course
from backend.app.seed.generator import database_counts

router = APIRouter(prefix="/api", tags=["meta"])
DB = Annotated[Session, Depends(get_db)]


@router.get("/health")
def health(request: Request, db: DB):
    """Public liveness probe. Record counts are only shown to a signed-in user."""
    db.execute(text("SELECT 1"))
    body = {"status": "ok", "database": "ok"}
    if find_session(request, db) is not None:
        body["counts"] = database_counts(db)
    return body


@router.get("/meta", response_model=schemas.Meta)
def meta(_principal: PrincipalDep, db: DB):
    return {
        "learning_styles": list(schemas.LearningStyle.__args__),
        "content_types": list(schemas.ContentType.__args__),
        "difficulties": list(schemas.Difficulty.__args__),
        "topics": list(db.scalars(select(Course.topic).distinct().order_by(Course.topic))),
        "enrollment_statuses": list(schemas.EnrollmentStatus.__args__),
    }
