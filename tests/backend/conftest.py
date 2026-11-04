import shutil

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.database import Database
from backend.app.main import create_app
from backend.app.ml_service import MLService
from backend.app.seed.generator import seed_database


@pytest.fixture(scope="session")
def seeded_template(tmp_path_factory):
    """Seed one database per test session; each test gets a fresh copy of it."""
    path = tmp_path_factory.mktemp("db") / "template.db"
    database = Database(f"sqlite:///{path.as_posix()}")
    database.create_all()
    with database.SessionLocal() as db:
        seed_database(db, random_state=42)
    database.engine.dispose()
    return path


@pytest.fixture(scope="session")
def trained_ml(seeded_template, tmp_path_factory):
    """ML models trained once on the seeded template (training takes several seconds)."""
    import os
    os.environ.setdefault("PLRS_REPORTS_DIR", str(tmp_path_factory.mktemp("reports")))
    database = Database(f"sqlite:///{seeded_template.as_posix()}")
    service = MLService()
    with database.SessionLocal() as db:
        service.train(db)
    database.engine.dispose()
    return service


def _client(db_source, tmp_path, ml_service=None):
    db_path = tmp_path / "test.db"
    shutil.copy(db_source, db_path)
    settings = Settings(database_url=f"sqlite:///{db_path.as_posix()}", seed_on_startup=False,
                        cors_origins=("http://localhost:5173",), ml_train_on_startup=False)
    return create_app(settings, ml_service=ml_service)


@pytest.fixture
def client(seeded_template, tmp_path):
    app = _client(seeded_template, tmp_path)
    with TestClient(app) as test_client:
        yield test_client
    app.state.database.engine.dispose()


@pytest.fixture
def ml_client(seeded_template, trained_ml, tmp_path):
    """Client whose app shares the pre-trained ML service (trained on the same data as the DB copy)."""
    app = _client(seeded_template, tmp_path, ml_service=trained_ml)
    with TestClient(app) as test_client:
        yield test_client
    app.state.database.engine.dispose()


@pytest.fixture
def new_student(client):
    response = client.post("/api/students", json={
        "name": "Test Learner", "email": "test.learner@example.edu", "age": 24,
        "learning_style": "Visual", "preferred_content": "Videos", "daily_goal_minutes": 45})
    assert response.status_code == 201, response.text
    return response.json()
