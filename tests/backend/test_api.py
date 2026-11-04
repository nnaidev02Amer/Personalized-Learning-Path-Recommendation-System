from datetime import date, timedelta

import pandas as pd
import pytest

from backend.app.database import Database
from backend.app.seed.generator import seed_database
from api_helpers import assert_error, course_id
from ml.config import SAMPLE_DATA_PATH


# ------------------------------------------------------------------ meta
def test_health_reports_seeded_counts(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    counts = body["counts"]
    assert counts["students"] == 100 and counts["courses"] == 24
    assert counts["lessons"] == 120 and counts["quiz_questions"] == 96


def test_meta(client):
    meta = client.get("/api/meta").json()
    assert len(meta["topics"]) == 6
    assert set(meta["learning_styles"]) == {"Auditory", "Kinesthetic", "Reading/Writing", "Visual"}


def test_unknown_route_returns_json_error(client):
    assert_error(client.get("/api/nope"), 404, "not_found")


def test_cors_allows_frontend_origin(client):
    r = client.get("/api/meta", headers={"Origin": "http://localhost:5173"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


# -------------------------------------------------------------- students
def test_list_students_pagination_search_filter(client):
    page = client.get("/api/students", params={"limit": 10, "offset": 20}).json()
    assert page["total"] == 100 and len(page["items"]) == 10
    assert page["items"][0]["id"] == 21
    visual = client.get("/api/students", params={"learning_style": "Visual", "limit": 100}).json()
    assert visual["total"] == 25 and all(s["learning_style"] == "Visual" for s in visual["items"])
    name = page["items"][0]["name"].split()[0]
    found = client.get("/api/students", params={"search": name}).json()["items"]
    assert any(s["id"] == 21 for s in found)


def test_seeded_students_keep_original_profile_values(client):
    original = pd.read_csv(SAMPLE_DATA_PATH).set_index("StudentID")
    for sid in (1, 50, 100):
        s = client.get(f"/api/students/{sid}").json()
        row = original.loc[sid]
        assert s["age"] == row.Age and s["learning_style"] == row.LearningStyle
        assert s["preferred_content"] == row.PreferredContent and s["is_synthetic"] is True
        summary = client.get(f"/api/students/{sid}/summary").json()
        assert summary["completed_courses"] == row.CompletedCourses
        # Seeded scores are whole correct answers out of 4 per quiz; the generator fixes the total
        # correct count to round(AverageScore% x questions), so the mean is within 50/N points.
        bound = 50 / (4 * summary["quizzes_taken"]) + 0.1
        assert abs(summary["average_quiz_score"] - row.AverageScore) <= bound


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1},
                                    {"learning_style": "Telepathic"}])
def test_list_students_rejects_bad_query(client, params):
    assert_error(client.get("/api/students", params=params), 422, "validation_error")


def test_get_missing_student(client):
    body = assert_error(client.get("/api/students/9999"), 404, "not_found")
    assert "9999" in body["message"]


def test_create_student(client, new_student):
    assert new_student["id"] == 101 and new_student["is_synthetic"] is False
    assert client.get("/api/students/101").json()["email"] == "test.learner@example.edu"


@pytest.mark.parametrize("override, field", [
    ({"email": "not-an-email"}, "email"), ({"age": 5}, "age"), ({"name": "   "}, "name"),
    ({"learning_style": "Telepathic"}, "learning_style"), ({"preferred_content": "TikTok"}, "preferred_content"),
    ({"daily_goal_minutes": 0}, "daily_goal_minutes"), ({"unexpected": 1}, "unexpected"),
])
def test_create_student_validation(client, override, field):
    payload = {"name": "A", "email": "a@example.edu", "age": 20, "preferred_content": "Videos", **override}
    body = assert_error(client.post("/api/students", json=payload), 422, "validation_error")
    assert any(field in d["field"] for d in body["details"])


def test_duplicate_email_conflict(client, new_student):
    payload = {"name": "Other", "email": "TEST.learner@example.edu", "age": 30, "preferred_content": "Articles"}
    assert_error(client.post("/api/students", json=payload), 409, "email_taken")


def test_update_student(client, new_student):
    r = client.patch(f"/api/students/{new_student['id']}", json={"age": 25, "learning_style": "Auditory"})
    assert r.status_code == 200 and r.json()["age"] == 25 and r.json()["learning_style"] == "Auditory"
    assert_error(client.patch(f"/api/students/{new_student['id']}", json={"name": None}), 422, "validation_error")
    taken = client.get("/api/students/1").json()["email"]
    assert_error(client.patch(f"/api/students/{new_student['id']}", json={"email": taken}), 409, "email_taken")


def test_delete_student_cascades(client):
    assert client.get("/api/students/5/enrollments").json()
    assert client.delete("/api/students/5").status_code == 204
    assert_error(client.get("/api/students/5"), 404, "not_found")
    assert_error(client.get("/api/students/5/enrollments"), 404, "not_found")
    assert client.get("/api/health").json()["counts"]["students"] == 99


# --------------------------------------------------------------- courses
def test_course_catalog_filters(client):
    all_courses = client.get("/api/courses").json()
    assert all_courses["total"] == 24
    beginners = client.get("/api/courses", params={"difficulty": "Beginner"}).json()["items"]
    assert beginners and all(c["difficulty"] == "Beginner" for c in beginners)
    ml = client.get("/api/courses", params={"topic": "Machine Learning"}).json()["items"]
    assert {c["code"] for c in ml} == {"ML201", "ML202", "ML301", "ML302"}
    podcasts = client.get("/api/courses", params={"content_format": "Podcasts"}).json()["items"]
    assert all(c["content_format"] == "Podcasts" for c in podcasts)
    assert client.get("/api/courses", params={"search": "pandas"}).json()["total"] >= 1
    assert any(c["average_rating"] is not None and c["enrolled_count"] > 0 for c in all_courses["items"])


def test_course_detail(client):
    course = client.get(f"/api/courses/{course_id(client, 'ML201')}").json()
    assert len(course["lessons"]) == 5 and course["lesson_count"] == 5
    assert {p["code"] for p in course["prerequisites"]} == {"PY102", "ST102", "DA101"}
    assert len(course["quizzes"]) == 1 and course["quizzes"][0]["question_count"] == 4
    assert_error(client.get("/api/courses/999"), 404, "not_found")


def test_quiz_does_not_leak_answers(client):
    course = client.get(f"/api/courses/{course_id(client, 'PY101')}").json()
    quiz = client.get(f"/api/quizzes/{course['quizzes'][0]['id']}").json()
    assert len(quiz["questions"]) == 4
    assert all("correct_option" not in q and "explanation" not in q for q in quiz["questions"])


# ---------------------------------------------------- end-to-end workflow
def test_full_learning_workflow(client, new_student):
    sid = new_student["id"]
    py101, py102 = course_id(client, "PY101"), course_id(client, "PY102")

    # Prerequisites are enforced.
    body = assert_error(client.post(f"/api/students/{sid}/enrollments", json={"course_id": py102}),
                        409, "prerequisites_not_met")
    assert body["details"][0]["code"] == "PY101"

    # Quiz requires enrolment.
    quiz_id = client.get(f"/api/courses/{py101}").json()["quizzes"][0]["id"]
    assert_error(client.post(f"/api/students/{sid}/quizzes/{quiz_id}/attempts", json={"answers": [0, 0, 0, 0]}),
                 409, "not_enrolled")

    enrollment = client.post(f"/api/students/{sid}/enrollments", json={"course_id": py101})
    assert enrollment.status_code == 201
    enrollment = enrollment.json()
    assert enrollment["status"] == "active" and enrollment["progress"] == 0
    assert enrollment["next_lesson"]["position"] == 1
    assert_error(client.post(f"/api/students/{sid}/enrollments", json={"course_id": py101}),
                 409, "already_enrolled")

    # Rating before completion is rejected.
    eid = enrollment["id"]
    assert_error(client.patch(f"/api/enrollments/{eid}", json={"rating": 5}), 409, "not_completed")

    lessons = client.get(f"/api/courses/{py101}").json()["lessons"]
    other_lesson = client.get(f"/api/courses/{py102}").json()["lessons"][0]["id"]
    assert_error(client.post(f"/api/enrollments/{eid}/lessons/{other_lesson}/complete"), 404, "not_found")

    for i, lesson in enumerate(lessons, start=1):
        state = client.post(f"/api/enrollments/{eid}/lessons/{lesson['id']}/complete").json()
        assert state["completed_lessons"] == i
    assert state["status"] == "completed" and state["progress"] == 1.0 and state["completed_at"]
    # Completing again is idempotent.
    again = client.post(f"/api/enrollments/{eid}/lessons/{lessons[0]['id']}/complete").json()
    assert again["completed_lessons"] == 5
    assert_error(client.patch(f"/api/enrollments/{eid}", json={"status": "dropped"}), 409, "invalid_status_change")
    assert client.patch(f"/api/enrollments/{eid}", json={"rating": 5}).json()["rating"] == 5

    # Quiz grading: answer keys come from the catalogue (PY101: 1, 2, 1, 2).
    result = client.post(f"/api/students/{sid}/quizzes/{quiz_id}/attempts",
                         json={"answers": [1, 2, 1, 0], "time_taken_min": 6.5})
    assert result.status_code == 201
    result = result.json()
    assert result["correct"] == 3 and result["total"] == 4 and result["score"] == 75.0
    assert result["passed"] is True
    assert [f["is_correct"] for f in result["feedback"]] == [True, True, True, False]
    assert result["feedback"][3]["correct_option"] == 2
    assert_error(client.post(f"/api/students/{sid}/quizzes/{quiz_id}/attempts", json={"answers": [1, 2]}),
                 422, "validation_error")
    assert_error(client.post(f"/api/students/{sid}/quizzes/{quiz_id}/attempts", json={"answers": [9, 0, 0, 0]}),
                 422, "validation_error")

    # Now PY102 is unlocked.
    assert client.post(f"/api/students/{sid}/enrollments", json={"course_id": py102}).status_code == 201

    summary = client.get(f"/api/students/{sid}/summary").json()
    assert summary["completed_courses"] == 1 and summary["active_courses"] == 1
    assert summary["lessons_completed"] == 5 and summary["lessons_pending"] == 5
    assert summary["quizzes_taken"] == 1 and summary["average_quiz_score"] == 75.0
    assert summary["current_streak_days"] == 1 and summary["minutes_last_7_days"] > 0

    progress = client.get(f"/api/students/{sid}/progress", params={"weeks": 4}).json()
    assert progress["overall_completion"] == 0.5
    assert len(progress["weekly_activity"]) == 4
    this_week = progress["weekly_activity"][-1]
    assert this_week["lessons"] == 5 and this_week["quizzes"] == 1
    assert progress["quiz_scores"][0]["score"] == 75.0
    attempts = client.get(f"/api/students/{sid}/quiz-attempts").json()
    assert attempts[0]["course_title"] == "Python Fundamentals"


def test_drop_and_reenroll(client, new_student):
    sid, py101 = new_student["id"], course_id(client, "PY101")
    eid = client.post(f"/api/students/{sid}/enrollments", json={"course_id": py101}).json()["id"]
    assert client.patch(f"/api/enrollments/{eid}", json={"status": "dropped"}).json()["status"] == "dropped"
    lesson = client.get(f"/api/courses/{py101}").json()["lessons"][0]["id"]
    assert_error(client.post(f"/api/enrollments/{eid}/lessons/{lesson}/complete"), 409, "enrollment_not_active")
    again = client.post(f"/api/students/{sid}/enrollments", json={"course_id": py101})
    assert again.status_code == 201 and again.json()["id"] == eid and again.json()["status"] == "active"


def test_manual_activity_log(client, new_student):
    sid = new_student["id"]
    r = client.post(f"/api/students/{sid}/activity", json={"minutes": 30})
    assert r.status_code == 201 and r.json()["kind"] == "study"
    future = (date.today() + timedelta(days=1)).isoformat()
    assert_error(client.post(f"/api/students/{sid}/activity", json={"minutes": 30, "activity_date": future}),
                 422, "validation_error")
    assert_error(client.post(f"/api/students/{sid}/activity", json={"minutes": 0}), 422, "validation_error")
    assert_error(client.post(f"/api/students/{sid}/activity", json={"minutes": 5, "course_id": 999}), 404, "not_found")
    assert len(client.get(f"/api/students/{sid}/activity").json()) == 1


def test_seeded_progress_report_shape(client):
    report = client.get("/api/students/1/progress").json()
    assert len(report["weekly_activity"]) == 12
    assert sum(w["minutes"] for w in report["weekly_activity"]) > 0
    assert 0 <= report["overall_completion"] <= 1
    assert report["score_trend"]["attempts"] == len(report["quiz_scores"])
    assert_error(client.get("/api/students/1/progress", params={"weeks": 0}), 422, "validation_error")


def test_seed_refuses_non_empty_database(seeded_template, tmp_path):
    import shutil
    path = tmp_path / "copy.db"
    shutil.copy(seeded_template, path)
    database = Database(f"sqlite:///{path.as_posix()}")
    with database.SessionLocal() as db, pytest.raises(RuntimeError, match="already contains data"):
        seed_database(db)
    database.engine.dispose()
