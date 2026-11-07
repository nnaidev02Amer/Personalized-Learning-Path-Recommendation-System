"""Student registration -> enrolment request -> admin approval -> study, the single administrator and the
user-reset tool."""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from api_helpers import assert_error
from backend.app import create_admin, reset_users
from backend.app.models import Course, User
from backend.app.security import hash_password
from conftest import ADMIN_EMAIL, ADMIN_PASSWORD, login

NEW = {"name": "Reg Student", "email": "reg.student@example.edu", "age": 22, "preferred_content": "Videos",
       "password": "A-Long-Passphrase-77"}


def register(app, **over):
    c = TestClient(app)
    r = c.post("/api/auth/register", json={**NEW, **over})
    assert r.status_code == 201, r.text
    c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    return c, r.json()["student"]["id"]


def basic_course(app):
    """An active course without prerequisites."""
    with app.state.database.SessionLocal() as db:
        return db.scalar(select(Course.id).where(Course.is_active.is_(True), ~Course.prerequisites.any()))


def test_full_flow_register_request_approve_study(app, client):
    student, sid = register(app)
    cid = basic_course(app)
    # direct enrolment is not available to students
    assert_error(student.post(f"/api/students/{sid}/enrollments", json={"course_id": cid}), 403, "approval_required")
    assert student.get(f"/api/students/{sid}/enrollments").json() == []

    r = student.post(f"/api/students/{sid}/enrollment-requests", json={"course_id": cid})
    assert r.status_code == 201 and r.json()["status"] == "pending"
    rid = r.json()["id"]
    assert student.get(f"/api/students/{sid}/enrollments").json() == []          # still not enrolled
    assert_error(student.post(f"/api/students/{sid}/enrollment-requests", json={"course_id": cid}), 409, "request_pending")

    # quizzes are closed until approval
    detail = client.get(f"/api/courses/{cid}").json()
    if detail["quizzes"]:
        assert student.get(f"/api/quizzes/{detail['quizzes'][0]['id']}").status_code == 404

    # a student cannot approve
    assert_error(student.post(f"/api/admin/enrollment-requests/{rid}/approve"), 403, "admin_required")

    overview = client.get("/api/admin/overview").json()
    assert overview["requests"]["pending"] == 1 and overview["students"]["registered"] == 1
    pending = client.get("/api/admin/enrollment-requests", params={"status": "pending"}).json()
    assert pending["total"] == 1 and pending["items"][0]["student_email"] == NEW["email"]

    ok = client.post(f"/api/admin/enrollment-requests/{rid}/approve")
    assert ok.status_code == 200 and ok.json()["status"] == "approved"
    mine = student.get(f"/api/students/{sid}/enrollments").json()
    assert len(mine) == 1 and mine[0]["course"]["id"] == cid and mine[0]["status"] == "active"
    lesson = mine[0]["next_lesson"]["id"]
    assert student.post(f"/api/enrollments/{mine[0]['id']}/lessons/{lesson}/complete").status_code == 200
    assert_error(client.post(f"/api/admin/enrollment-requests/{rid}/approve"), 409, "request_not_pending")

    per_course = {c["course_id"]: c for c in client.get("/api/admin/course-enrollments").json()}
    assert per_course[cid]["active"] >= 1 and per_course[cid]["pending_requests"] == 0
    after = client.get("/api/admin/overview").json()["requests"]
    assert after == {"pending": 0, "approved": 1, "rejected": 0}


def test_reject_request_again_and_cancel(app, client):
    student, sid = register(app)
    cid = basic_course(app)
    rid = student.post(f"/api/students/{sid}/enrollment-requests", json={"course_id": cid}).json()["id"]
    r = client.post(f"/api/admin/enrollment-requests/{rid}/reject", json={"note": "Class is full"})
    assert r.json()["status"] == "rejected" and r.json()["note"] == "Class is full"
    assert student.get(f"/api/students/{sid}/enrollments").json() == []
    listed = student.get(f"/api/students/{sid}/enrollment-requests").json()
    assert listed[0]["status"] == "rejected" and listed[0]["note"] == "Class is full"

    again = student.post(f"/api/students/{sid}/enrollment-requests", json={"course_id": cid})
    assert again.status_code == 201
    assert student.delete(f"/api/students/{sid}/enrollment-requests/{again.json()['id']}").status_code == 204
    assert_error(client.post(f"/api/admin/enrollment-requests/{again.json()['id']}/approve"), 409,
                 "request_not_pending")


def test_prerequisites_and_isolation(app, client):
    a, sa_ = register(app)
    b, sb = register(app, email="second@example.edu", name="Second Student")
    with app.state.database.SessionLocal() as db:
        locked = db.scalar(select(Course.id).where(Course.is_active.is_(True), Course.prerequisites.any()))
    assert_error(a.post(f"/api/students/{sa_}/enrollment-requests", json={"course_id": locked}), 409,
                 "prerequisites_not_met")
    cid = basic_course(app)
    rid = a.post(f"/api/students/{sa_}/enrollment-requests", json={"course_id": cid}).json()["id"]
    # another student can neither see, create for, nor withdraw it
    assert b.get(f"/api/students/{sa_}/enrollment-requests").status_code == 404
    assert b.post(f"/api/students/{sa_}/enrollment-requests", json={"course_id": cid}).status_code == 404
    assert b.delete(f"/api/students/{sb}/enrollment-requests/{rid}").status_code == 404
    assert b.get("/api/admin/enrollment-requests").status_code == 403
    assert b.get("/api/admin/overview").status_code == 403


def test_registration_cannot_create_an_administrator(app):
    c = TestClient(app)
    assert c.post("/api/auth/register", json={**NEW, "role": "admin"}).status_code == 422


def test_only_one_administrator_can_exist(app):
    with app.state.database.SessionLocal() as db:       # the database itself refuses a second one
        db.add(User(email="second.admin@example.test", password_hash=hash_password("x" * 12), role="admin"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        assert db.query(User).filter_by(role="admin").count() == 1


def test_create_admin_command_refuses_a_second_admin(app, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", app.state.settings.database_url)
    code = create_admin.main(["--email", "other@example.test", "--generate-password"])
    assert code == 1 and "already exists" in capsys.readouterr().err
    code = create_admin.main(["--email", ADMIN_EMAIL, "--reset-password", "--generate-password"])
    out = capsys.readouterr().out
    assert code == 0 and "Password (shown once" in out
    new_password = out.split(": ", 1)[1].strip().splitlines()[0]
    assert len(new_password) >= 20
    login(app, ADMIN_EMAIL, new_password)
    login(app, ADMIN_EMAIL, ADMIN_PASSWORD, expect=401)


def test_reset_users_backs_up_and_keeps_courses_and_sample_learners(app, client, monkeypatch):
    student, sid = register(app)
    cid = basic_course(app)
    rid = student.post(f"/api/students/{sid}/enrollment-requests", json={"course_id": cid}).json()["id"]
    client.post(f"/api/admin/enrollment-requests/{rid}/approve")
    url = app.state.settings.database_url
    path = url.replace("sqlite:///", "")
    monkeypatch.setenv("DATABASE_URL", url)

    def snapshot():
        with sqlite3.connect(path) as raw:
            return {t: raw.execute(f"select count(*) from {t}").fetchone()[0]
                    for t in ("users", "students", "courses", "lessons", "quizzes", "enrollments")}

    before = snapshot()
    assert reset_users.main([]) == 0 and snapshot() == before            # dry run changes nothing
    assert reset_users.main(["--apply"]) == 0
    after = snapshot()
    assert after["users"] == 0
    assert after["students"] == before["students"] - 1                   # only the registered student's profile
    for table in ("courses", "lessons", "quizzes"):
        assert after[table] == before[table]
    with sqlite3.connect(path) as raw:
        assert raw.execute("select count(*) from students where is_synthetic = 1").fetchone()[0] == after["students"]
        assert raw.execute("select count(*) from enrollment_requests").fetchone()[0] == 0
    backups = list((Path(path).parent / "backups").glob("*.bak"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as raw:                              # the backup still holds everything
        assert raw.execute("select count(*) from users").fetchone()[0] == before["users"]
    # a fresh administrator can be created afterwards
    assert create_admin.main(["--email", "new.admin@example.test", "--generate-password"]) == 0


# ------------------------------------------------------------------ lock / unlock / hide
def test_unlocked_courses_are_direct_and_locked_ones_need_approval(app, client):
    student, sid = register(app)
    cid = basic_course(app)
    assert client.get(f"/api/courses/{cid}").json()["is_locked"] is True            # existing behaviour: locked
    assert_error(student.post(f"/api/students/{sid}/enrollments", json={"course_id": cid}), 403, "approval_required")

    assert client.patch(f"/api/courses/{cid}", json={"is_locked": False}).json()["is_locked"] is False
    assert_error(student.post(f"/api/students/{sid}/enrollment-requests", json={"course_id": cid}), 409,
                 "course_unlocked")                                                  # no request needed any more
    r = student.post(f"/api/students/{sid}/enrollments", json={"course_id": cid})
    assert r.status_code == 201 and r.json()["status"] == "active"                   # direct access

    # locking again does not take the course away from someone already enrolled
    client.patch(f"/api/courses/{cid}", json={"is_locked": True})
    assert len(student.get(f"/api/students/{sid}/enrollments").json()) == 1


def test_only_the_admin_can_lock_unlock_hide_create_delete(app, client):
    student, sid = register(app)
    cid = basic_course(app)
    for call in (lambda: student.patch(f"/api/courses/{cid}", json={"is_locked": False}),
                 lambda: student.patch(f"/api/courses/{cid}", json={"is_active": False}),
                 lambda: student.delete(f"/api/courses/{cid}")):
        assert_error(call(), 403, "admin_required")
    assert client.get(f"/api/courses/{cid}").json()["is_locked"] is True


def test_hidden_courses_leave_the_student_catalogue_and_cannot_be_requested(app, client):
    student, sid = register(app)
    cid = basic_course(app)
    in_catalogue = lambda: any(c["id"] == cid for c in student.get("/api/courses", params={"limit": 100}).json()["items"])  # noqa: E731
    assert in_catalogue()
    assert client.patch(f"/api/courses/{cid}", json={"is_active": False}).json()["is_active"] is False
    assert not in_catalogue()
    assert_error(student.get(f"/api/courses/{cid}"), 404, "not_found")
    assert_error(student.post(f"/api/students/{sid}/enrollment-requests", json={"course_id": cid}), 409, "course_archived")
    assert any(c["id"] == cid for c in client.get("/api/courses", params={"include_archived": True, "limit": 100}).json()["items"])
    client.patch(f"/api/courses/{cid}", json={"is_active": True})
    assert in_catalogue()


def test_admin_creates_a_locked_course_and_deletes_an_unused_one(app, client):
    body = {"code": "LK-101", "title": "Locked one", "description": "d", "topic": "Programming", "difficulty": "Beginner",
            "content_format": "Videos", "duration_hours": 2, "skills": ["x"], "is_locked": True,
            "lessons": [{"title": "One", "duration_min": 10}]}
    made = client.post("/api/courses", json=body)
    assert made.status_code == 201 and made.json()["is_locked"] is True
    student, sid = register(app)
    assert_error(student.post(f"/api/students/{sid}/enrollments", json={"course_id": made.json()["id"]}), 403,
                 "approval_required")
    assert client.delete(f"/api/courses/{made.json()['id']}").status_code == 204
