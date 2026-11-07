import shutil
from itertools import count

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.database import Database
from backend.app.main import create_app
from backend.app.ml_service import MLService
from backend.app.models import User
from backend.app.security import hash_password
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


ADMIN_EMAIL = "admin@example.test"
ADMIN_PASSWORD = "Test-Admin-Pass-123"          # test-only; never a real credential
STUDENT_PASSWORD = "Test-Student-Pass-123"
_emails = count(1)


def login(app, email, password, *, expect=200):
    """A fresh client (own cookie jar) signed in as ``email``; sends the CSRF token on every request."""
    c = TestClient(app)
    response = c.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == expect, response.text
    if expect == 200:
        c.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return c


def add_admin(app, email=ADMIN_EMAIL, password=ADMIN_PASSWORD):
    with app.state.database.SessionLocal() as db:
        db.add(User(email=email, password_hash=hash_password(password), role="admin"))
        db.commit()


def _client(db_source, tmp_path, ml_service=None):
    db_path = tmp_path / "test.db"
    shutil.copy(db_source, db_path)
    settings = Settings(database_url=f"sqlite:///{db_path.as_posix()}", seed_on_startup=False,
                        cors_origins=("http://localhost:5173",), ml_train_on_startup=False)
    return create_app(settings, ml_service=ml_service)


@pytest.fixture
def app(seeded_template, tmp_path):
    application = _client(seeded_template, tmp_path)
    with TestClient(application):          # runs start-up / shut-down
        add_admin(application)
        yield application
    application.state.database.engine.dispose()


@pytest.fixture
def client(app):
    """Signed in as an ADMINISTRATOR (so the pre-authentication API tests keep exercising the full API)."""
    return login(app, ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture
def anon(app):
    """Not signed in."""
    return TestClient(app)


@pytest.fixture
def ml_app(seeded_template, trained_ml, tmp_path):
    application = _client(seeded_template, tmp_path, ml_service=trained_ml)
    with TestClient(application):
        add_admin(application)
        yield application
    application.state.database.engine.dispose()


@pytest.fixture
def ml_client(ml_app):
    """Admin client whose app shares the pre-trained ML service (trained on the same data as the DB copy)."""
    return login(ml_app, ADMIN_EMAIL, ADMIN_PASSWORD)


def create_learner(app, admin, prefix="learner", password=STUDENT_PASSWORD):
    """An admin-created learner with a login -> (signed-in client, student id, email)."""
    n = next(_emails)
    email = f"{prefix}{n}@example.edu"
    response = admin.post("/api/admin/users", json={
        "name": f"{prefix.title()} {n}", "email": email, "age": 23, "preferred_content": "Videos",
        "password": password})
    assert response.status_code == 201, response.text
    return login(app, email, password), response.json()["student_id"], email


@pytest.fixture
def make_student(app, client):
    """Factory for learners on the plain app (no trained models)."""
    return lambda prefix="learner", password=STUDENT_PASSWORD: create_learner(app, client, prefix, password)


@pytest.fixture
def make_ml_student(ml_app, ml_client):
    """Factory for learners on the app with trained ML models."""
    return lambda prefix="learner", password=STUDENT_PASSWORD: create_learner(ml_app, ml_client, prefix, password)


@pytest.fixture
def new_student(client):
    response = client.post("/api/students", json={
        "name": "Test Learner", "email": "test.learner@example.edu", "age": 24,
        "learning_style": "Visual", "preferred_content": "Videos", "daily_goal_minutes": 45})
    assert response.status_code == 201, response.text
    return response.json()
