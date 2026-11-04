"""FastAPI application factory.

Run locally (from the repository root):

    uvicorn backend.app.main:app --reload

Interactive API docs: http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from backend.app.config import Settings, get_settings
from backend.app.database import Database
from backend.app.errors import install_error_handlers
from backend.app.models import Course
from backend.app.routers import courses, learning, meta, students

log = logging.getLogger("backend")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    database = Database(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database.create_all()
        if settings.seed_on_startup:
            with database.SessionLocal() as db:
                if db.scalar(select(Course.id).limit(1)) is None:
                    from backend.app.seed.generator import seed_database
                    counts = seed_database(db, random_state=settings.seed_random_state)
                    log.info("Seeded empty database: %s", counts)
        yield
        database.engine.dispose()

    app = FastAPI(title="Personalized Learning Path API", version="2.0.0",
                  description="Students, courses, enrolments, quizzes and progress analytics.",
                  lifespan=lifespan)
    app.state.database = database
    app.state.settings = settings
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                       allow_methods=["*"], allow_headers=["*"])
    install_error_handlers(app)
    for router in (meta.router, students.router, courses.router, learning.router):
        app.include_router(router)
    return app


app = create_app()
