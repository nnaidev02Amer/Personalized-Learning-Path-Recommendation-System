"""AI / ML endpoints.

* Model status, evaluation and retraining: administrators only.
* Per-student model outputs: the student themself or an administrator. Most accept an optional
  ``course_id`` that limits the view to one of the student's enrolled courses.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app import assistant, services
from backend.app.auth import AdminDep, StudentDep
from backend.app.deps import get_db
from backend.app.models import RecommendationHistory, Student

router = APIRouter(prefix="/api", tags=["ai"])
DB = Annotated[Session, Depends(get_db)]
CourseId = Annotated[int | None, Query(gt=0, description="Limit to one enrolled course")]


def ml(request: Request):
    return request.app.state.ml


# ------------------------------------------------------------------ admin only
@router.get("/ml/status")
def ml_status(_admin: AdminDep, request: Request):
    svc = ml(request)
    return {"trained": svc.ready, "trained_at": svc.trained_at,
            "training_data": svc.report.get("training_data") if svc.report else None,
            "assistant_provider": assistant.provider()}


@router.get("/ml/evaluation")
def ml_evaluation(_admin: AdminDep, request: Request, db: DB):
    svc = ml(request)
    svc.ensure_trained(db)
    return svc.report


@router.post("/ml/retrain")
def ml_retrain(_admin: AdminDep, request: Request, db: DB):
    report = ml(request).train(db)
    return {"trained_at": report["trained_at"], "training_seconds": report["training_seconds"]}


# ---------------------------------------------------------- per-student outputs
def _log_recommendations(db: Session, student_id: int, course_id: int | None, method: str, result: dict) -> None:
    """Keep a history of what was recommended; a new row only when the list actually changed."""
    items = [{"course_id": i["course_id"], "code": i["code"], "title": i["title"], "score": i["score"],
              "reasons": i["reasons"]} for i in result["items"]]
    if not items:
        return
    last = db.scalar(select(RecommendationHistory).where(
        RecommendationHistory.student_id == student_id, RecommendationHistory.method == method,
        RecommendationHistory.course_id.is_(None) if course_id is None else RecommendationHistory.course_id == course_id,
    ).order_by(RecommendationHistory.id.desc()).limit(1))
    if last is not None and [i["course_id"] for i in last.items] == [i["course_id"] for i in items]:
        return
    db.add(RecommendationHistory(student_id=student_id, course_id=course_id, method=method, items=items,
                                 model_trained_at=result.get("trained_at")))
    db.commit()


@router.get("/students/{student_id}/recommendations")
def recommendations(student: StudentDep, request: Request, db: DB, course_id: CourseId = None,
                    method: Literal["hybrid", "content", "collaborative", "popularity"] = "hybrid",
                    limit: int = Query(5, ge=1, le=20)):
    result = ml(request).recommendations(db, student.id, method=method, limit=limit, course_id=course_id)
    _log_recommendations(db, student.id, course_id, method, result)
    return result


@router.get("/students/{student_id}/recommendation-history")
def recommendation_history(student: StudentDep, db: DB, limit: int = Query(20, ge=1, le=100)):
    rows = db.scalars(select(RecommendationHistory).where(RecommendationHistory.student_id == student.id)
                      .order_by(RecommendationHistory.id.desc()).limit(limit)).all()
    return {"student_id": student.id,
            "items": [{"id": r.id, "created_at": r.created_at, "method": r.method, "course_id": r.course_id,
                       "items": r.items, "model_trained_at": r.model_trained_at} for r in rows]}


@router.get("/students/{student_id}/learning-style")
def learning_style(student: StudentDep, request: Request, db: DB):
    return ml(request).learning_style(db, student.id)


@router.get("/students/{student_id}/skills")
def skills(student: StudentDep, request: Request, db: DB, course_id: CourseId = None):
    return ml(request).skills(db, student.id, course_id)


@router.get("/students/{student_id}/adaptive-difficulty")
def adaptive_difficulty(student: StudentDep, request: Request, db: DB, course_id: CourseId = None):
    return ml(request).adaptive_difficulty(db, student.id, course_id)


@router.get("/students/{student_id}/predictions")
def predictions(student: StudentDep, request: Request, db: DB, course_id: CourseId = None):
    return ml(request).predictions(db, student.id, course_id)


@router.get("/students/{student_id}/courses/{course_id}/guidance")
def course_guidance(student: StudentDep, course_id: int, request: Request, db: DB):
    """Skills, difficulty, quiz predictions and next steps for one enrolled course."""
    return ml(request).guidance(db, student.id, course_id)


class AssistantQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=1000)


@router.post("/students/{student_id}/assistant")
def ask_assistant(student: StudentDep, data: AssistantQuestion, request: Request, db: DB):
    svc = ml(request)
    student_id = student.id
    ctx = {
        "student": {"name": student.name, "learning_style_self_reported": student.learning_style,
                    "preferred_content": student.preferred_content,
                    "history": "synthetic (seeded)" if student.is_synthetic else "real"},
        "summary": services.student_summary(db, student),
        "recommendations": svc.recommendations(db, student_id),
        "skills": svc.skills(db, student_id),
        "difficulty": svc.adaptive_difficulty(db, student_id),
        "predictions": svc.predictions(db, student_id),
        "learning_style": svc.learning_style(db, student_id),
    }
    ctx["summary"] = {k: v for k, v in ctx["summary"].items() if k != "student"}
    result = assistant.answer(data.message.strip(), ctx)
    return {"student_id": student_id, "question": data.message.strip(), **result,
            "grounded_on": ["progress summary", "hybrid recommendations", "BKT skill mastery",
                            "LinUCB difficulty", "score prediction", "learning-style model"]}
