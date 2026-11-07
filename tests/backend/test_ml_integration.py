"""Integration edge cases for the ML service (Phase 6)."""

import threading

from fastapi.testclient import TestClient
from conftest import ADMIN_EMAIL, ADMIN_PASSWORD, add_admin, login

from api_helpers import assert_error
from backend.app.config import Settings
from backend.app.database import Database
from backend.app.main import create_app
from backend.app.ml_service import MLService


def test_concurrent_first_requests_train_only_once(seeded_template, monkeypatch):
    """Several AI requests arriving before training finished must not each retrain."""
    service = MLService()
    calls = []
    original = MLService.train

    def counting_train(self, db):
        calls.append(1)
        return original(self, db)

    monkeypatch.setattr(MLService, "train", counting_train)
    database = Database(f"sqlite:///{seeded_template.as_posix()}")

    def worker():
        with database.SessionLocal() as db:
            service.ensure_trained(db)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    database.engine.dispose()
    assert service.ready
    assert len(calls) == 1, f"trained {len(calls)} times"


def test_ml_endpoints_report_insufficient_data_clearly(tmp_path):
    """An empty database (seeding disabled) must give a clear 503, not a 500 crash."""
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'empty.db').as_posix()}", seed_on_startup=False,
                        ml_train_on_startup=False, cors_origins=("http://localhost:5173",))
    app = create_app(settings)
    with TestClient(app):
        add_admin(app)
        client = login(app, ADMIN_EMAIL, ADMIN_PASSWORD)
        body = assert_error(client.get("/api/ml/evaluation"), 503, "ml_insufficient_data")
        assert "quiz attempts" in body["message"]
        sid = client.post("/api/students", json={"name": "Solo", "email": "solo@example.edu", "age": 30,
                                                 "preferred_content": "Videos"}).json()["id"]
        assert_error(client.get(f"/api/students/{sid}/recommendations"), 503, "ml_insufficient_data")
        assert client.get("/api/ml/status").json()["trained"] is False
        assert client.get("/api/health").status_code == 200       # rest of the API unaffected
    app.state.database.engine.dispose()


def test_new_student_has_sensible_cold_start_outputs(ml_client):
    sid = ml_client.post("/api/students", json={"name": "Cold", "email": "cold@example.edu", "age": 25,
                                                "preferred_content": "Articles"}).json()["id"]
    assert ml_client.get(f"/api/students/{sid}/skills").json()["skills"] == []
    assert ml_client.get(f"/api/students/{sid}/predictions").json()["items"] == []
    style = ml_client.get(f"/api/students/{sid}/learning-style").json()
    assert style["predicted_style"] and style["self_reported_style"] is None
    diff = ml_client.get(f"/api/students/{sid}/adaptive-difficulty").json()
    assert diff["context"]["experience"] == 0.0
    answer = ml_client.post(f"/api/students/{sid}/assistant", json={"message": "Which skills are weak?"}).json()
    assert answer["answer"]


def test_outputs_update_when_student_data_changes(ml_client):
    """Enrol -> predictions appear; finish lessons + quiz -> skills, recommendations, difficulty change."""
    sid = ml_client.post("/api/students", json={"name": "Flow", "email": "flow@example.edu", "age": 22,
                                                "preferred_content": "Videos"}).json()["id"]
    py101 = next(c for c in ml_client.get("/api/courses", params={"search": "PY101"}).json()["items"]
                 if c["code"] == "PY101")
    before_recs = [i["code"] for i in ml_client.get(f"/api/students/{sid}/recommendations",
                                                    params={"limit": 20}).json()["items"]]
    assert "PY101" in before_recs and "PY102" not in before_recs

    eid = ml_client.post(f"/api/students/{sid}/enrollments", json={"course_id": py101["id"]}).json()["id"]
    preds = ml_client.get(f"/api/students/{sid}/predictions").json()["items"]
    assert [p["course_id"] for p in preds] == [py101["id"]] and preds[0]["previous_attempts"] == 0

    for lesson in ml_client.get(f"/api/courses/{py101['id']}").json()["lessons"]:
        ml_client.post(f"/api/enrollments/{eid}/lessons/{lesson['id']}/complete")
    quiz_id = ml_client.get(f"/api/courses/{py101['id']}").json()["quizzes"][0]["id"]
    diff_before = ml_client.get(f"/api/students/{sid}/adaptive-difficulty").json()["context"]
    ml_client.post(f"/api/students/{sid}/quizzes/{quiz_id}/attempts", json={"answers": [1, 2, 1, 2]})

    after_recs = [i["code"] for i in ml_client.get(f"/api/students/{sid}/recommendations",
                                                   params={"limit": 20}).json()["items"]]
    assert "PY101" not in after_recs and "PY102" in after_recs
    skills = {s["skill"]: s for s in ml_client.get(f"/api/students/{sid}/skills").json()["skills"]}
    assert skills["control-flow"]["observations"] == 2 and skills["control-flow"]["mastered"]
    diff_after = ml_client.get(f"/api/students/{sid}/adaptive-difficulty").json()["context"]
    assert diff_after["prior_mean"] == 1.0 and diff_before["prior_mean"] == 0.75   # 100% score vs default
    preds = ml_client.get(f"/api/students/{sid}/predictions").json()["items"]
    assert preds[0]["previous_attempts"] == 1 and preds[0]["status"] == "completed"
