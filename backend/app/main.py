"""FastAPI application factory.

Run locally (from the repository root):

    uvicorn backend.app.main:app --reload

Interactive API docs: http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from backend.app.config import Settings, get_settings
from backend.app.database import Database
from backend.app.errors import InsufficientData, install_error_handlers
from backend.app.ml_service import MLService
from backend.app.security import RateLimiter
from backend.app.models import Course
from backend.app.routers import admin, auth as auth_router, courses, learning, meta, students
from backend.app.routers import ml as ml_router

log = logging.getLogger("backend")


def _train_in_background(database: Database, ml_service: MLService) -> None:
    def run():
        try:
            with database.SessionLocal() as db:
                ml_service.ensure_trained(db)
        except InsufficientData as exc:
            log.info("ML models not trained yet: %s", exc.message)
        except Exception:   # never crash the server because of training
            log.exception("Background ML training failed; models will train on first ML request")
    threading.Thread(target=run, name="ml-training", daemon=True).start()


def create_app(settings: Settings | None = None, ml_service: MLService | None = None) -> FastAPI:
    settings = settings or get_settings()
    database = Database(settings.database_url)
    ml_service = ml_service or MLService()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database.create_all()
        if settings.seed_on_startup:
            with database.SessionLocal() as db:
                if db.scalar(select(Course.id).limit(1)) is None:
                    from backend.app.seed.generator import seed_database
                    counts = seed_database(db, random_state=settings.seed_random_state)
                    log.info("Seeded empty database: %s", counts)
        if settings.ml_train_on_startup and not ml_service.ready:
            _train_in_background(database, ml_service)
        yield
        database.engine.dispose()

    app = FastAPI(title="Personalized Learning Path API", version="2.0.0",
                  description="Students, courses, enrolments, quizzes and progress analytics.",
                  lifespan=lifespan)
    app.state.database = database
    app.state.settings = settings
    app.state.ml = ml_service
    app.state.limiter = RateLimiter()

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")   # never cache per-user API data
        return response

    # Explicit origins + credentials (cookie sessions). Never "*".
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=True,
                       allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
                       allow_headers=["Content-Type", "X-CSRF-Token"])
    install_error_handlers(app)
    for router in (meta.router, auth_router.router, students.router, courses.router, learning.router,
                   ml_router.router, admin.router):
        app.include_router(router)
    return app


app = create_app()
