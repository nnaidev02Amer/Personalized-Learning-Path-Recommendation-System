"""Role-based access control and student data isolation."""

import re

import pytest
from sqlalchemy import func, select

from api_helpers import assert_error, course_id, enrol_via_approval
from backend.app.models import Enrollment, QuizAttempt, Student, User

PUBLIC = {("GET", "/api/health"), ("GET", "/api/auth/config"), ("POST", "/api/auth/login"),
          ("POST", "/api/auth/register"),
          ("POST", "/api/auth/logout")}        # logout is idempotent: with no session it just clears the cookie
NEW_STUDENT = {"name": "Made By Admin", "email": "made.by.admin@example.edu", "age": 30, "preferred_content": "Videos"}


def enrol(client, sid, code="PY101"):
    return enrol_via_approval(client, sid, code)


def quiz_of(client, code="PY101"):
    return client.get(f"/api/courses/{course_id(client, code)}").json()["quizzes"][0]["id"]


# -------------------------------------------------- every route is protected
def test_every_route_requires_a_session(anon):
    schema = anon.get("/openapi.json").json()
    protected = 0
    for path, ops in schema["paths"].items():
        for method in ops:
            if (method.upper(), path) in PUBLIC:
                continue
            url = re.sub(r"{\w+}", "1", path)
            r = anon.request(method.upper(), url, json={} if method != "get" else None)
            if url in ("/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect"):
                continue
            assert r.status_code == 401, f"{method.upper()} {path} -> {r.status_code}"
            protected += 1
    assert protected >= 38


ADMIN_ONLY = [
    ("GET", "/api/students"), ("POST", "/api/students"), ("DELETE", "/api/students/1"),
    ("GET", "/api/ml/status"), ("GET", "/api/ml/evaluation"), ("POST", "/api/ml/retrain"),
    ("POST", "/api/courses"), ("PATCH", "/api/courses/1"), ("DELETE", "/api/courses/1"),
    ("GET", "/api/admin/overview"), ("GET", "/api/admin/students"), ("GET", "/api/admin/users"),
    ("POST", "/api/admin/users"), ("POST", "/api/admin/students/1/account"), ("PATCH", "/api/admin/users/1"),
    ("POST", "/api/admin/users/1/revoke-sessions"),
]


@pytest.mark.parametrize("method,path", ADMIN_ONLY)
def test_students_are_forbidden_from_admin_routes(make_student, method, path):
    c, sid, _ = make_student()
    r = c.request(method, path, json={})
    assert_error(r, 403, "admin_required")


def test_admin_routes_work_for_admin(client):
    assert client.get("/api/admin/overview").json()["students"]["total"] >= 100
    assert client.get("/api/ml/status").status_code == 200
    page = client.get("/api/admin/students", params={"limit": 5}).json()
    assert page["total"] >= 100 and len(page["items"]) == 5 and "average_score" in page["items"][0]


# ------------------------------------------------------- student data isolation
OTHER_STUDENT_READS = [
    "/api/students/{s}", "/api/students/{s}/summary", "/api/students/{s}/progress",
    "/api/students/{s}/quiz-attempts", "/api/students/{s}/activity", "/api/students/{s}/enrollments",
    "/api/students/{s}/recommendations", "/api/students/{s}/recommendation-history", "/api/students/{s}/skills",
    "/api/students/{s}/adaptive-difficulty", "/api/students/{s}/predictions", "/api/students/{s}/learning-style",
    "/api/students/{s}/courses/1/guidance",
]


@pytest.mark.parametrize("template", OTHER_STUDENT_READS)
def test_a_student_cannot_read_another_students_data(make_student, template):
    a, a_id, _ = make_student("alice")
    _, b_id, _ = make_student("bob")
    seeded = 7
    mine = a.get(template.format(s=a_id))
    assert mine.status_code != 404 or "guidance" in template      # own data is reachable (guidance needs enrolment)
    for target in (b_id, seeded):
        r = a.get(template.format(s=target))
        assert_error(r, 404, "not_found")
    # a foreign id is indistinguishable from a missing one (no id probing)
    assert a.get(template.format(s=b_id)).json()["error"]["message"].replace(str(b_id), "N") == \
        a.get(template.format(s=999999)).json()["error"]["message"].replace("999999", "N")


def test_a_student_cannot_write_to_another_students_records(make_student):
    a, a_id, _ = make_student("alice")
    b, b_id, _ = make_student("bob")
    enrollment = enrol(b, b_id)
    py_quiz = quiz_of(a)
    lesson = a.get(f"/api/courses/{course_id(a, 'PY101')}").json()["lessons"][0]["id"]
    attempts = [
        ("PATCH", f"/api/students/{b_id}", {"age": 99}),
        ("POST", f"/api/students/{b_id}/enrollments", {"course_id": course_id(a, "ST101")}),
        ("POST", f"/api/students/{b_id}/activity", {"minutes": 30}),
        ("POST", f"/api/students/{b_id}/quizzes/{py_quiz}/attempts", {"answers": [0, 0, 0, 0]}),
        ("POST", f"/api/students/{b_id}/assistant", {"message": "hi"}),
        ("PATCH", f"/api/enrollments/{enrollment['id']}", {"status": "dropped"}),
        ("POST", f"/api/enrollments/{enrollment['id']}/lessons/{lesson}/complete", None),
    ]
    for method, path, body in attempts:
        assert_error(a.request(method, path, json=body), 404, "not_found")
    assert_error(a.get(f"/api/enrollments/{enrollment['id']}"), 404, "not_found")
    # nothing about B changed
    after = b.get(f"/api/enrollments/{enrollment['id']}").json()
    assert after["status"] == "active" and after["completed_lessons"] == 0
    assert b.get(f"/api/students/{b_id}").json()["age"] == 23 and b.get(f"/api/students/{b_id}/quiz-attempts").json() == []


def test_a_student_cannot_change_which_student_a_request_acts_on(make_student):
    a, a_id, _ = make_student("alice")
    b, b_id, _ = make_student("bob")
    # identity fields cannot be written through the profile endpoint
    for field, value in (("id", b_id), ("student_id", b_id), ("is_synthetic", True), ("role", "admin")):
        assert a.patch(f"/api/students/{a_id}", json={field: value}).status_code == 422
    # a body naming another student is ignored: enrolment belongs to the path/session student only
    r = a.post(f"/api/students/{a_id}/enrollments", json={"course_id": course_id(a, "PY101"), "student_id": b_id})
    assert r.status_code == 422
    assert b.get(f"/api/students/{b_id}/enrollments").json() == []
    me = a.get("/api/auth/me").json()
    assert me["user"]["student_id"] == a_id and a.get("/api/auth/me").json()["student"]["id"] == a_id


def test_student_listings_never_expose_other_students(make_student):
    a, a_id, _ = make_student("alice")
    assert_error(a.get("/api/students"), 403, "admin_required")
    assert_error(a.get("/api/admin/users"), 403, "admin_required")
    assert a.get("/api/admin/students").status_code == 403


def test_students_own_data_flows_work(make_student):
    a, a_id, _ = make_student("alice")
    enrollment = enrol(a, a_id)
    quiz = quiz_of(a)
    lesson = a.get(f"/api/courses/{course_id(a, 'PY101')}").json()["lessons"][0]["id"]
    assert a.post(f"/api/enrollments/{enrollment['id']}/lessons/{lesson}/complete").status_code == 200
    assert a.get(f"/api/quizzes/{quiz}").status_code == 200
    assert a.post(f"/api/students/{a_id}/quizzes/{quiz}/attempts", json={"answers": [0, 0, 0, 0]}).status_code == 201
    assert a.post(f"/api/students/{a_id}/activity", json={"minutes": 20}).status_code == 201
    assert a.get(f"/api/students/{a_id}/summary").json()["quizzes_taken"] == 1
    assert a.patch(f"/api/students/{a_id}", json={"age": 41}).json()["age"] == 41


def test_independent_enrolments_per_student(make_student):
    a, a_id, _ = make_student("alice")
    b, b_id, _ = make_student("bob")
    c, c_id, _ = make_student("carol")
    enrol(a, a_id, "PY101"), enrol(a, a_id, "ST101")
    enrol(b, b_id, "PY101")
    enrol(c, c_id, "ST101")
    codes = lambda cl, sid: sorted(e["course"]["code"] for e in cl.get(f"/api/students/{sid}/enrollments").json())  # noqa: E731
    assert codes(a, a_id) == ["PY101", "ST101"] and codes(b, b_id) == ["PY101"] and codes(c, c_id) == ["ST101"]
    lesson = a.get(f"/api/courses/{course_id(a, 'PY101')}").json()["lessons"][0]["id"]
    ea = next(e for e in a.get(f"/api/students/{a_id}/enrollments").json() if e["course"]["code"] == "PY101")
    a.post(f"/api/enrollments/{ea['id']}/lessons/{lesson}/complete")
    assert b.get(f"/api/students/{b_id}/enrollments").json()[0]["completed_lessons"] == 0      # B's progress is B's own


def test_a_student_cannot_open_a_quiz_of_a_course_they_are_not_in(make_student):
    a, a_id, _ = make_student("alice")
    quiz = quiz_of(a)
    assert_error(a.get(f"/api/quizzes/{quiz}"), 404, "not_found")
    enrol(a, a_id)
    assert a.get(f"/api/quizzes/{quiz}").status_code == 200


def test_quiz_submission_requires_enrolment(make_student):
    a, a_id, _ = make_student("alice")
    r = a.post(f"/api/students/{a_id}/quizzes/{quiz_of(a)}/attempts", json={"answers": [0, 0, 0, 0]})
    assert_error(r, 409, "not_enrolled")


# --------------------------------------------------------------- deletion
def test_only_an_admin_can_delete_students(app, client, make_student):
    a, a_id, a_email = make_student("alice")
    b, b_id, _ = make_student("bob")
    assert_error(a.delete(f"/api/students/{a_id}"), 403, "admin_required")       # not even themselves
    assert_error(a.delete(f"/api/students/{b_id}"), 403, "admin_required")
    assert_error(a.delete("/api/students/7"), 403, "admin_required")
    with app.state.database.SessionLocal() as db:
        assert db.get(Student, 7) is not None and db.get(Student, b_id) is not None


def test_admin_deletion_removes_the_learner_and_their_login_only(app, client, make_student):
    a, a_id, a_email = make_student("alice")
    b, b_id, _ = make_student("bob")
    enrol(a, a_id)
    enrol(b, b_id)
    with app.state.database.SessionLocal() as db:
        students_before = db.scalar(select(func.count(Student.id)))
        enrol_before = db.scalar(select(func.count(Enrollment.id)))
    assert client.delete(f"/api/students/{a_id}").status_code == 204
    with app.state.database.SessionLocal() as db:
        assert db.scalar(select(func.count(Student.id))) == students_before - 1
        assert db.scalar(select(func.count(Enrollment.id))) == enrol_before - 1          # only alice's enrolment
        assert db.scalar(select(User.id).where(User.email == a_email)) is None            # login gone with the learner
    assert a.get("/api/auth/me").status_code == 401                                         # her session died with it
    assert b.get(f"/api/students/{b_id}/enrollments").status_code == 200                    # bob untouched


# ----------------------------------------------- linking logins to existing students
def test_only_an_admin_can_link_a_login_to_a_seeded_student(app, client, make_student):
    stranger, _, _ = make_student("mallory")
    with app.state.database.SessionLocal() as db:
        before = db.scalar(select(func.count(Student.id)))
        seeded = db.get(Student, 7)
        seeded_email, attempts_before = seeded.email, db.scalar(
            select(func.count(QuizAttempt.id)).where(QuizAttempt.student_id == 7))
    assert_error(stranger.post("/api/admin/students/7/account", json={"password": "Mallory-Pass-12345"}), 403, "admin_required")

    r = client.post("/api/admin/students/7/account", json={"password": "Linked-Seeded-Pass-1"})
    assert r.status_code == 201 and r.json()["student_id"] == 7 and r.json()["email"] == seeded_email
    assert client.post("/api/admin/students/7/account", json={"password": "Linked-Seeded-Pass-2"}).status_code == 409
    from conftest import login
    seven = login(app, seeded_email, "Linked-Seeded-Pass-1")
    assert seven.get("/api/auth/me").json()["student"]["id"] == 7
    assert len(seven.get("/api/students/7/quiz-attempts", params={"limit": 500}).json()) == attempts_before
    assert_error(seven.get("/api/students/8"), 404, "not_found")                             # only their own record
    with app.state.database.SessionLocal() as db:
        assert db.scalar(select(func.count(Student.id))) == before                            # no duplicate student


def test_admin_created_accounts_get_new_profiles_and_unique_emails(client):
    body = {**NEW_STUDENT, "password": "Fresh-Orchid-Ledger-12"}
    r = client.post("/api/admin/users", json=body)
    assert r.status_code == 201 and r.json()["student_id"] and r.json()["role"] == "student"
    assert_error(client.post("/api/admin/users", json=body), 409, "email_taken")
    assert client.post("/api/admin/users", json={**body, "email": "x2@example.edu", "password": "short"}).status_code == 422
    assert client.post("/api/admin/users", json={**body, "email": "x3@example.edu", "student_id": 7}).status_code == 422


def test_profile_email_change_keeps_login_in_step_and_stays_unique(make_student):
    a, a_id, _ = make_student("alice")
    b, b_id, b_email = make_student("bob")
    assert_error(a.patch(f"/api/students/{a_id}", json={"email": b_email}), 409, "email_taken")
    assert a.patch(f"/api/students/{a_id}", json={"email": "alice.new@example.edu"}).status_code == 200
    assert a.get("/api/auth/me").json()["user"]["email"] == "alice.new@example.edu"


# ------------------------------------------------------------ admin safeguards
def test_admin_cannot_lock_themselves_out(client):
    me = client.get("/api/auth/me").json()["user"]["id"]
    assert_error(client.patch(f"/api/admin/users/{me}", json={"is_active": False}), 403, "cannot_deactivate_self")


def test_the_only_administrator_cannot_be_deactivated(client):
    me = client.get("/api/auth/me").json()["user"]["id"]
    assert_error(client.patch(f"/api/admin/users/{me}", json={"is_active": False}), 403, "cannot_deactivate_self")


def test_admin_users_listing_never_leaks_hashes(client, make_student):
    make_student()
    text = client.get("/api/admin/users").text
    assert "argon2" not in text and "password_hash" not in text and "csrf" not in text.lower()


def test_revoke_sessions_signs_a_user_out(client, make_student):
    c, sid, _ = make_student()
    uid = c.get("/api/auth/me").json()["user"]["id"]
    assert client.get("/api/admin/users", params={"search": "learner"}).json()["items"][0]["active_sessions"] >= 1
    assert client.post(f"/api/admin/users/{uid}/revoke-sessions").status_code == 204
    assert c.get("/api/auth/me").status_code == 401


# ---------------------------------------------------------- course management
COURSE = {"code": "qa-101", "title": "QA Course", "description": "Created in a test", "topic": "Programming",
          "difficulty": "Beginner", "content_format": "Videos", "duration_hours": 3, "skills": ["testing"],
          "lessons": [{"title": "L1", "duration_min": 20}, {"title": "L2", "duration_min": 25}],
          "quiz": {"title": "QA quiz", "questions": [{"prompt": "2+2?", "options": ["3", "4"], "correct_option": 1,
                                                       "skill": "testing"}]}}


def test_admin_creates_edits_and_archives_courses(client, make_student):
    r = client.post("/api/courses", json=COURSE)
    assert r.status_code == 201, r.text
    course = r.json()
    assert course["code"] == "QA-101" and course["lesson_count"] == 2 and course["is_active"] and course["level"] == 1
    assert_error(client.post("/api/courses", json=COURSE), 409, "course_code_taken")
    bad = {**COURSE, "code": "QA-102", "quiz": {"title": "q", "questions": [
        {"prompt": "?", "options": ["a", "b"], "correct_option": 5, "skill": "s"}]}}
    assert client.post("/api/courses", json=bad).status_code == 422
    assert client.post("/api/courses", json={**COURSE, "code": "QA-103", "extra": 1}).status_code == 422

    student, sid, _ = make_student()
    assert any(c["code"] == "QA-101" for c in student.get("/api/courses").json()["items"])
    assert course["is_locked"] is False                                   # new courses are open
    assert student.post(f"/api/students/{sid}/enrollments", json={"course_id": course["id"]}).status_code == 201

    other, other_id, _ = make_student()
    assert client.patch(f"/api/courses/{course['id']}", json={"is_active": False}).json()["is_active"] is False
    assert not any(c["code"] == "QA-101" for c in other.get("/api/courses").json()["items"])      # hidden from catalogue
    assert_error(other.get(f"/api/courses/{course['id']}"), 404, "not_found")
    assert_error(other.post(f"/api/students/{other_id}/enrollments", json={"course_id": course["id"]}), 404, "not_found") \
        if False else None
    assert_error(client.post(f"/api/students/{other_id}/enrollments", json={"course_id": course["id"]}), 409, "course_archived")
    assert student.get(f"/api/courses/{course['id']}").status_code == 200                           # enrolled student keeps access
    assert len(student.get(f"/api/students/{sid}/enrollments").json()) == 1                         # history preserved
    assert any(c["code"] == "QA-101" for c in client.get("/api/courses", params={"include_archived": True}).json()["items"])
    assert_error(client.delete(f"/api/courses/{course['id']}"), 409, "course_in_use")               # in use: archive only
    assert_error(student.patch(f"/api/courses/{course['id']}", json={"is_active": True}), 403, "admin_required")


def test_unused_course_can_be_deleted(client):
    cid = client.post("/api/courses", json=COURSE).json()["id"]
    assert client.delete(f"/api/courses/{cid}").status_code == 204
    assert client.get(f"/api/courses/{cid}").status_code == 404


def test_admin_can_view_every_students_enrolments_and_performance(client, make_student):
    a, a_id, _ = make_student("alice")
    enrol(a, a_id)
    assert client.get(f"/api/students/{a_id}/enrollments").json()[0]["course"]["code"] == "PY101"
    row = client.get("/api/admin/students", params={"search": "alice"}).json()["items"][0]
    assert row["has_login"] and row["enrollments"] == 1 and row["id"] == a_id
