"""AI/ML endpoints on the seeded database with real trained models."""

import pytest

from api_helpers import assert_error, course_id
from backend.app import assistant


# ------------------------------------------------------------ status & eval
def test_status_and_evaluation_report(ml_client):
    status = ml_client.get("/api/ml/status").json()
    assert status["trained"] is True and status["training_data"]["synthetic_students"] == 100
    report = ml_client.get("/api/ml/evaluation").json()
    for section in ("recommendations", "knowledge_tracing", "performance_prediction", "learning_style",
                    "adaptive_difficulty", "training_data"):
        assert section in report
    recs = report["recommendations"]
    for protocol in recs["protocols"].values():
        assert {"hybrid", "content", "collaborative", "popularity", "random"} <= set(protocol["methods"])
        for cmp in protocol["vs_popularity_ndcg"].values():
            lo, hi = cmp["ci95"]
            assert lo <= cmp["improvement"] <= hi
            assert cmp["significant"] == (lo > 0)
    # Every comparison flag is backed by a bootstrap CI.
    assert report["knowledge_tracing"]["beats_best_baseline"] == (report["knowledge_tracing"]["vs_best_baseline_log_loss"]["ci95"][0] > 0)
    assert report["performance_prediction"]["beats_baseline"] == (report["performance_prediction"]["vs_best_baseline_abs_error"]["ci95"][0] > 0)
    assert report["adaptive_difficulty"]["beats_baseline"] == (report["adaptive_difficulty"]["vs_arm_mean_brier"]["ci95"][0] > 0)
    assert "SYNTHETIC" in report["training_data"]["note"]


# ----------------------------------------------------------- recommendations
def test_recommendations_are_unlocked_and_untaken(ml_client):
    enrolled = {e["course"]["id"] for e in ml_client.get("/api/students/1/enrollments").json()}
    completed_codes = {e["course"]["code"] for e in ml_client.get("/api/students/1/enrollments").json()
                       if e["status"] == "completed"}
    courses = {c["id"]: c for c in ml_client.get("/api/courses").json()["items"]}
    for method in ("hybrid", "content", "collaborative", "popularity"):
        body = ml_client.get("/api/students/1/recommendations", params={"method": method, "limit": 10}).json()
        assert body["method"] == method and body["model_output"] is True
        assert body["student_history"].startswith("synthetic")
        scores = [i["score"] for i in body["items"]]
        assert scores == sorted(scores, reverse=True)
        # (the shared trained model may know a throw-away course another test created; this DB copy does not)
        for item in (i for i in body["items"] if i["course_id"] in courses):
            assert item["course_id"] not in enrolled
            assert set(courses[item["course_id"]]["prerequisite_codes"]) <= completed_codes
            assert item["reasons"]


def test_cold_start_student_gets_beginner_courses_in_preferred_format_first(ml_client):
    sid = ml_client.post("/api/students", json={"name": "New", "email": "new@example.edu", "age": 30,
                                                "preferred_content": "Podcasts"}).json()["id"]
    body = ml_client.get(f"/api/students/{sid}/recommendations").json()
    assert body["items"] and all(i["difficulty_level"] == 1 for i in body["items"])
    assert body["student_history"].startswith("real")
    assert_error(ml_client.get(f"/api/students/{sid}/recommendations", params={"method": "magic"}),
                 422, "validation_error")
    assert_error(ml_client.get("/api/students/9999/recommendations"), 404, "not_found")


def test_recommendations_react_to_new_enrolment(ml_client):
    sid = ml_client.post("/api/students", json={"name": "Py", "email": "py@example.edu", "age": 20,
                                                "preferred_content": "Videos"}).json()["id"]
    py101 = course_id(ml_client, "PY101")
    eid = ml_client.post(f"/api/students/{sid}/enrollments", json={"course_id": py101}).json()["id"]
    for lesson in ml_client.get(f"/api/courses/{py101}").json()["lessons"]:
        ml_client.post(f"/api/enrollments/{eid}/lessons/{lesson['id']}/complete")
    codes = [i["code"] for i in ml_client.get(f"/api/students/{sid}/recommendations",
                                              params={"limit": 20}).json()["items"]]
    assert "PY101" not in codes and "PY102" in codes     # unlocked by completing PY101


# --------------------------------------------------------------- BKT skills
def test_skill_mastery_and_gaps(ml_client):
    body = ml_client.get("/api/students/7/skills").json()
    assert 0 < body["params"]["p_init"] < 1 and body["threshold"] == 0.6
    for s in body["skills"]:
        assert 0 <= s["mastery"] <= 1 and s["observations"] >= 1
        assert s["mastered"] == (s["mastery"] >= 0.6)
    assert all(not g["mastered"] for g in body["gaps"])
    masteries = [s["mastery"] for s in body["skills"]]
    assert masteries == sorted(masteries)


def test_wrong_answers_lower_mastery(ml_client):
    sid = ml_client.post("/api/students", json={"name": "Q", "email": "q@example.edu", "age": 20,
                                                "preferred_content": "Videos"}).json()["id"]
    py101 = course_id(ml_client, "PY101")
    ml_client.post(f"/api/students/{sid}/enrollments", json={"course_id": py101})
    quiz_id = ml_client.get(f"/api/courses/{py101}").json()["quizzes"][0]["id"]
    ml_client.post(f"/api/students/{sid}/quizzes/{quiz_id}/attempts", json={"answers": [0, 0, 0, 0]})   # all wrong
    skills = {s["skill"]: s for s in ml_client.get(f"/api/students/{sid}/skills").json()["skills"]}
    p_init = ml_client.get(f"/api/students/{sid}/skills").json()["params"]["p_init"]
    assert skills["python-basics"]["mastery"] < p_init
    assert skills["python-basics"]["accuracy"] == 0


# -------------------------------------------------------- adaptive difficulty
def test_adaptive_difficulty_and_online_update(ml_client):
    body = ml_client.get("/api/students/1/adaptive-difficulty").json()
    assert body["recommended_level"] in (1, 2, 3) and len(body["arms"]) == 3
    assert all(0 <= a["expected_success"] <= 1 for a in body["arms"])
    before = {a["level"]: a["observations"] for a in body["arms"]}
    # Submitting a quiz updates the bandit online.
    py101 = course_id(ml_client, "PY101")
    sid = ml_client.post("/api/students", json={"name": "B", "email": "b@example.edu", "age": 20,
                                                "preferred_content": "Videos"}).json()["id"]
    ml_client.post(f"/api/students/{sid}/enrollments", json={"course_id": py101})
    quiz_id = ml_client.get(f"/api/courses/{py101}").json()["quizzes"][0]["id"]
    ml_client.post(f"/api/students/{sid}/quizzes/{quiz_id}/attempts", json={"answers": [1, 2, 1, 0]})
    after = {a["level"]: a["observations"] for a in ml_client.get("/api/students/1/adaptive-difficulty").json()["arms"]}
    assert after[1] == before[1] + 1 and after[2] == before[2] and after[3] == before[3]


# ------------------------------------------------------ performance & style
def test_predictions_for_enrolled_courses(ml_client):
    body = ml_client.get("/api/students/1/predictions").json()
    enrolled = {e["course"]["id"] for e in ml_client.get("/api/students/1/enrollments").json() if e["status"] != "dropped"}
    assert {i["course_id"] for i in body["items"]} == enrolled
    for i in body["items"]:
        assert 0 <= i["predicted_score"] <= 100 and i["expected_error_mae"] > 0
        assert i["pass_probability_hint"] in {"likely", "uncertain", "at risk"}


def test_learning_style_reports_reliability(ml_client):
    body = ml_client.get("/api/students/1/learning-style").json()
    assert body["predicted_style"] in {"Auditory", "Kinesthetic", "Reading/Writing", "Visual"}
    assert abs(sum(body["probabilities"].values()) - 1) < 1e-3     # values rounded to 4 decimals
    assert body["self_reported_style"] == "Kinesthetic"
    if not body["reliable"]:
        assert "does not beat" in body["advice"]


# ----------------------------------------------------------------- assistant
@pytest.fixture
def rules_mode(monkeypatch):
    monkeypatch.setenv("ASSISTANT_PROVIDER", "rules")


def test_assistant_rules_mode_is_grounded(ml_client, rules_mode):
    recs = ml_client.get("/api/students/1/recommendations").json()["items"]
    body = ml_client.post("/api/students/1/assistant", json={"message": "What should I learn next?"}).json()
    assert body["source"] == "rules" and body["intent"] == "recommend"
    assert recs[0]["title"] in body["answer"]
    style = ml_client.post("/api/students/1/assistant", json={"message": "What is my learning style?"}).json()
    assert style["intent"] == "style" and "Kinesthetic" in style["answer"]
    progress = ml_client.post("/api/students/1/assistant", json={"message": "How am I doing?"}).json()
    summary = ml_client.get("/api/students/1/summary").json()
    assert f"completed {summary['completed_courses']} course" in progress["answer"]


def test_assistant_validation(ml_client):
    assert_error(ml_client.post("/api/students/1/assistant", json={"message": ""}), 422, "validation_error")
    assert_error(ml_client.post("/api/students/999/assistant", json={"message": "hi"}), 404, "not_found")


def test_assistant_uses_claude_when_configured(ml_client, monkeypatch):
    monkeypatch.setenv("ASSISTANT_PROVIDER", "claude")
    seen = {}

    def fake_claude(message, ctx):
        seen["ctx"] = ctx
        return "Grounded answer from Claude.", "claude-opus-5-5"

    monkeypatch.setattr(assistant, "_claude_answer", fake_claude)
    body = ml_client.post("/api/students/1/assistant", json={"message": "Which skills are weak?"}).json()
    assert body["source"] == "claude" and body["model"] == "claude-opus-5-5"
    assert body["answer"] == "Grounded answer from Claude."
    assert {"recommendations", "skills", "difficulty", "predictions", "learning_style"} <= set(seen["ctx"])


def test_assistant_falls_back_when_claude_fails(ml_client, monkeypatch):
    import anthropic
    monkeypatch.setenv("ASSISTANT_PROVIDER", "claude")

    def broken(message, ctx):
        raise anthropic.APIConnectionError(request=None)

    monkeypatch.setattr(assistant, "_claude_answer", broken)
    body = ml_client.post("/api/students/1/assistant", json={"message": "How am I doing?"}).json()
    assert body["source"] == "rules" and "Could not reach the Claude API" in body["note"]
    assert body["answer"]
