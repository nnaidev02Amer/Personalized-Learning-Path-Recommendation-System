"""AI / ML endpoints: model status & evaluation, per-student model outputs, assistant."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from backend.app import assistant, services
from backend.app.deps import get_db
from backend.app.models import Student

router = APIRouter(prefix="/api", tags=["ai"])
DB = Annotated[Session, Depends(get_db)]


def ml(request: Request):
    return request.app.state.ml


@router.get("/ml/status")
def ml_status(request: Request):
    svc = ml(request)
    return {"trained": svc.ready, "trained_at": svc.trained_at,
            "training_data": svc.report.get("training_data") if svc.report else None,
            "assistant_provider": assistant.provider()}


@router.get("/ml/evaluation")
def ml_evaluation(request: Request, db: DB):
    svc = ml(request)
    svc.ensure_trained(db)
    return svc.report


@router.post("/ml/retrain")
def ml_retrain(request: Request, db: DB):
    report = ml(request).train(db)
    return {"trained_at": report["trained_at"], "training_seconds": report["training_seconds"]}


@router.get("/students/{student_id}/recommendations")
def recommendations(student_id: int, request: Request, db: DB,
                    method: Literal["hybrid", "content", "collaborative", "popularity"] = "hybrid",
                    limit: int = Query(5, ge=1, le=20)):
    return ml(request).recommendations(db, student_id, method=method, limit=limit)


@router.get("/students/{student_id}/learning-style")
def learning_style(student_id: int, request: Request, db: DB):
    return ml(request).learning_style(db, student_id)


@router.get("/students/{student_id}/skills")
def skills(student_id: int, request: Request, db: DB):
    return ml(request).skills(db, student_id)


@router.get("/students/{student_id}/adaptive-difficulty")
def adaptive_difficulty(student_id: int, request: Request, db: DB):
    return ml(request).adaptive_difficulty(db, student_id)


@router.get("/students/{student_id}/predictions")
def predictions(student_id: int, request: Request, db: DB):
    return ml(request).predictions(db, student_id)


class AssistantQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=1000)


@router.post("/students/{student_id}/assistant")
def ask_assistant(student_id: int, data: AssistantQuestion, request: Request, db: DB):
    svc = ml(request)
    student = services.get_or_404(db, Student, student_id)
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
