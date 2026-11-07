"""Course-scoped ML inference and per-student isolation of model outputs.

The models are trained jointly on all learners (unchanged methodology); these tests check that what a
student is shown is computed from THEIR rows, and that a course scope only ever narrows it to an
enrolled course.
"""

import json

import pytest
from sqlalchemy import select

from api_helpers import assert_error, course_id, enrol_via_approval
from backend.app.models import Course, RecommendationHistory


def enrol(c, sid, code):
    return enrol_via_approval(c, sid, code)


def quiz_of(c, code):
    return c.get(f"/api/courses/{course_id(c, code)}").json()["quizzes"][0]["id"]


def answer_key(admin, quiz_id, sid_for_probe):
    """Correct answers, learned from a probe attempt's feedback (the quiz endpoint never exposes them)."""
    r = admin.post(f"/api/students/{sid_for_probe}/quizzes/{quiz_id}/attempts", json={"answers": [0, 0, 0, 0]})
    return [f["correct_option"] for f in r.json()["feedback"]]


def course_skills(c, code):
    body = c.get(f"/api/courses/{course_id(c, code)}").json()
    return set(body["skills"])


def test_models_expose_the_scope_and_the_shared_training_disclosure(make_ml_student):
    a, a_id, _ = make_ml_student("alice")
    enrol(a, a_id, "PY101")
    cid = course_id(a, "PY101")
    g = a.get(f"/api/students/{a_id}/courses/{cid}/guidance")
    assert g.status_code == 200, g.text
    body = g.json()
    assert body["scope"] == {"course_id": cid, "course_code": "PY101", "course_title": body["scope"]["course_title"]}
    assert "no separate per-course models" in body["note"] and "trained jointly" in body["note"]
    assert body["actions"] and all(isinstance(x, str) for x in body["actions"])
    assert body["skills"]["scope"]["course_id"] == body["difficulty"]["scope"]["course_id"] == cid


def test_scope_is_limited_to_courses_the_student_is_enrolled_in(make_ml_student):
    a, a_id, _ = make_ml_student("alice")
    enrol(a, a_id, "PY101")
    other = course_id(a, "ST101")                                   # real course, but alice is not in it
    for path in ("skills", "adaptive-difficulty", "predictions", "recommendations"):
        assert_error(a.get(f"/api/students/{a_id}/{path}", params={"course_id": other}), 404, "not_found")
    assert_error(a.get(f"/api/students/{a_id}/courses/{other}/guidance"), 404, "not_found")
    assert_error(a.get(f"/api/students/{a_id}/skills", params={"course_id": 999999}), 404, "not_found")
    assert a.get(f"/api/students/{a_id}/skills", params={"course_id": 0}).status_code == 422


def test_skills_and_predictions_are_course_specific(make_ml_student):
    a, a_id, _ = make_ml_student("alice")
    enrol(a, a_id, "PY101")
    enrol(a, a_id, "ST101")
    py, st = course_id(a, "PY101"), course_id(a, "ST101")
    for code, cid in (("PY101", py), ("ST101", st)):
        a.post(f"/api/students/{a_id}/quizzes/{quiz_of(a, code)}/attempts", json={"answers": [0, 0, 0, 0]})
    scoped = a.get(f"/api/students/{a_id}/skills", params={"course_id": py}).json()
    assert scoped["skills"] and {s["skill"] for s in scoped["skills"]} <= course_skills(a, "PY101")
    other = a.get(f"/api/students/{a_id}/skills", params={"course_id": st}).json()
    assert {s["skill"] for s in other["skills"]} <= course_skills(a, "ST101")
    everything = a.get(f"/api/students/{a_id}/skills").json()
    assert {s["skill"] for s in everything["skills"]} >= {s["skill"] for s in scoped["skills"]}

    all_pred = a.get(f"/api/students/{a_id}/predictions").json()["items"]
    py_pred = a.get(f"/api/students/{a_id}/predictions", params={"course_id": py}).json()["items"]
    assert {p["course_id"] for p in all_pred} == {py, st} and {p["course_id"] for p in py_pred} == {py}


def test_adaptive_difficulty_context_uses_only_the_scoped_courses_attempts(make_ml_student):
    a, a_id, _ = make_ml_student("alice")
    enrol(a, a_id, "PY101")
    enrol(a, a_id, "ST101")
    py, st = course_id(a, "PY101"), course_id(a, "ST101")
    for _ in range(3):
        a.post(f"/api/students/{a_id}/quizzes/{quiz_of(a, 'PY101')}/attempts", json={"answers": [0, 0, 0, 0]})
    scoped_st = a.get(f"/api/students/{a_id}/adaptive-difficulty", params={"course_id": st}).json()
    scoped_py = a.get(f"/api/students/{a_id}/adaptive-difficulty", params={"course_id": py}).json()
    whole = a.get(f"/api/students/{a_id}/adaptive-difficulty").json()
    assert scoped_st["context"] != scoped_py["context"]              # ST101 has no attempts: a different (empty) context
    assert whole["context"] == scoped_py["context"]                  # all of alice's attempts are in PY101
    assert scoped_st["scope"]["course_id"] == st


def test_recommendations_for_a_course_are_related_and_never_archived(ml_client, make_ml_student):
    a, a_id, _ = make_ml_student("alice")
    enrol(a, a_id, "PY101")
    py = course_id(a, "PY101")
    topic = a.get(f"/api/courses/{py}").json()["topic"]
    scoped = a.get(f"/api/students/{a_id}/recommendations", params={"course_id": py, "limit": 10}).json()
    assert scoped["scope"]["course_id"] == py
    unlocked_by_py = {c["id"] for c in ml_client.get("/api/courses", params={"limit": 100}).json()["items"]
                      if "PY101" in c["prerequisite_codes"]}
    assert all(i["topic"] == topic or i["course_id"] in unlocked_by_py for i in scoped["items"])
    assert all(i["course_id"] != py for i in scoped["items"])         # never re-recommends what is already taken
    if scoped["items"]:
        victim = scoped["items"][0]["course_id"]
        assert ml_client.patch(f"/api/courses/{victim}", json={"is_active": False}).status_code == 200
        after = a.get(f"/api/students/{a_id}/recommendations", params={"limit": 20}).json()["items"]
        assert victim not in {i["course_id"] for i in after}


def test_one_students_activity_does_not_change_another_students_outputs(make_ml_student):
    a, a_id, _ = make_ml_student("alice")
    b, b_id, _ = make_ml_student("bob")
    enrol(a, a_id, "PY101")
    enrol(b, b_id, "PY101")
    snapshot = lambda: {  # noqa: E731
        "skills": json.dumps(b.get(f"/api/students/{b_id}/skills").json()["skills"], sort_keys=True),
        "pred": json.dumps(b.get(f"/api/students/{b_id}/predictions").json()["items"], sort_keys=True),
        "recs": json.dumps(b.get(f"/api/students/{b_id}/recommendations").json()["items"], sort_keys=True),
        "style": json.dumps(b.get(f"/api/students/{b_id}/learning-style").json().get("probabilities"), sort_keys=True)}
    before = snapshot()
    for _ in range(3):                                               # alice fails the PY101 quiz three times
        a.post(f"/api/students/{a_id}/quizzes/{quiz_of(a, 'PY101')}/attempts", json={"answers": [0, 0, 0, 0]})
    lesson = a.get(f"/api/courses/{course_id(a, 'PY101')}").json()["lessons"][0]["id"]
    a.post(f"/api/enrollments/{a.get(f'/api/students/{a_id}/enrollments').json()[0]['id']}/lessons/{lesson}/complete")
    assert snapshot() == before                                      # bob's mastery, predictions, recs, style: unchanged
    # ...while alice's own outputs did react to alice's record
    assert any(s["accuracy"] == 0 for s in a.get(f"/api/students/{a_id}/skills").json()["skills"])


def test_each_students_skills_come_from_their_own_answers(ml_client, make_ml_student):
    weak, w_id, _ = make_ml_student("weak")
    strong, s_id, _ = make_ml_student("strong")
    enrol(weak, w_id, "PY101")
    enrol(strong, s_id, "PY101")
    quiz = quiz_of(weak, "PY101")
    key = answer_key(ml_client, quiz, w_id)                          # one probe attempt on weak's own record
    for _ in range(2):
        weak.post(f"/api/students/{w_id}/quizzes/{quiz}/attempts", json={"answers": [(k + 1) % 2 for k in key]})
        strong.post(f"/api/students/{s_id}/quizzes/{quiz}/attempts", json={"answers": key})
    mean = lambda c, sid: sum(s["mastery"] for s in c.get(f"/api/students/{sid}/skills").json()["skills"])  # noqa: E731
    assert mean(strong, s_id) > mean(weak, w_id) + 0.3


# --------------------------------------------------------- recommendation history
def test_recommendation_history_is_saved_deduplicated_and_private(ml_app, make_ml_student):
    a, a_id, _ = make_ml_student("alice")
    b, b_id, _ = make_ml_student("bob")
    enrol(a, a_id, "PY101")
    for _ in range(3):
        a.get(f"/api/students/{a_id}/recommendations")                 # identical list: stored once
    rows = a.get(f"/api/students/{a_id}/recommendation-history").json()["items"]
    assert len(rows) == 1 and rows[0]["method"] == "hybrid" and rows[0]["items"] and rows[0]["course_id"] is None
    a.get(f"/api/students/{a_id}/recommendations", params={"method": "popularity"})
    a.get(f"/api/students/{a_id}/recommendations", params={"course_id": course_id(a, "PY101")})
    kinds = {(r["method"], r["course_id"]) for r in a.get(f"/api/students/{a_id}/recommendation-history").json()["items"]}
    assert ("hybrid", None) in kinds and ("popularity", None) in kinds
    assert b.get(f"/api/students/{b_id}/recommendation-history").json()["items"] == []
    assert_error(b.get(f"/api/students/{a_id}/recommendation-history"), 404, "not_found")
    with ml_app.state.database.SessionLocal() as db:
        assert {r.student_id for r in db.scalars(select(RecommendationHistory))} == {a_id}


# ------------------------------------------------------------- existing ML intact
def test_model_evaluation_is_admin_only_but_unchanged_for_admin(ml_client, make_ml_student):
    a, a_id, _ = make_ml_student("alice")
    for path in ("/api/ml/evaluation", "/api/ml/status"):
        assert_error(a.get(path), 403, "admin_required")
    assert_error(a.post("/api/ml/retrain"), 403, "admin_required")
    report = ml_client.get("/api/ml/evaluation").json()
    assert {"recommendations", "knowledge_tracing", "performance_prediction", "adaptive_difficulty",
            "learning_style"} <= set(report)
    assert report["performance_prediction"]["model"].startswith("ability-anchored")


def test_unscoped_outputs_keep_their_original_shape(ml_client):
    s = ml_client.get("/api/students/7/skills").json()
    assert {"skills", "gaps", "not_yet_assessed", "topics", "params", "threshold"} <= set(s) and s["scope"] is None
    p = ml_client.get("/api/students/7/predictions").json()
    assert p["items"] and p["scope"] is None
    d = ml_client.get("/api/students/7/adaptive-difficulty").json()
    assert {"recommended_difficulty", "arms", "context"} <= set(d)
    r = ml_client.get("/api/students/7/recommendations").json()
    assert r["items"] and r["method"] == "hybrid" and r["scope"] is None
