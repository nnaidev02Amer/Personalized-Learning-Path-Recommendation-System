"""Every route in the OpenAPI schema is exercised and documented (Phase 6)."""

import re

from ml_helpers import ROOT

# Bodies for write endpoints; ids are filled from a freshly created student/enrolment.
BODIES = {
    ("POST", "/api/students"): {"name": "Cov", "email": "cov@example.edu", "age": 30, "preferred_content": "Videos"},
    ("PATCH", "/api/students/{student_id}"): {"age": 31},
    ("POST", "/api/students/{student_id}/activity"): {"minutes": 15},
    ("POST", "/api/students/{student_id}/enrollments"): None,     # filled with PY101 id
    ("POST", "/api/students/{student_id}/enrollment-requests"): None,   # filled with a free course id
    ("POST", "/api/admin/enrollment-requests/{request_id}/reject"): {"note": "Not this term"},
    ("PATCH", "/api/enrollments/{enrollment_id}"): {"status": "active"},
    ("POST", "/api/students/{student_id}/quizzes/{quiz_id}/attempts"): {"answers": [1, 2, 1, 2]},
    ("POST", "/api/students/{student_id}/assistant"): {"message": "How am I doing?"},
}
BODIES.update({
    ("POST", "/api/courses"): {
        "code": "COV-101", "title": "Coverage course", "description": "d", "topic": "Programming",
        "difficulty": "Beginner", "content_format": "Videos", "duration_hours": 2, "skills": ["coverage"],
        "lessons": [{"title": "One", "duration_min": 10}],
        "quiz": {"title": "Q", "questions": [{"prompt": "?", "options": ["a", "b"], "correct_option": 0, "skill": "coverage"}]}},
    ("PATCH", "/api/courses/{course_id}"): {"duration_hours": 7},
    ("POST", "/api/admin/users"): {"name": "Cov Admin-made", "email": "cov.made@example.edu", "age": 28,
                                   "preferred_content": "Videos", "password": "Coverage-Pass-123"},
    ("POST", "/api/admin/students/{student_id}/account"): {"password": "Coverage-Pass-456"},
    ("PATCH", "/api/admin/users/{user_id}"): {"unlock": True},
    ("POST", "/api/auth/login"): {"email": "admin@example.test", "password": "Test-Admin-Pass-123"},
})
SUCCESS = {"GET": 200, "PATCH": 200, "DELETE": 204}
EXPECT = {("POST", "/api/auth/register"): 201,               # registration is open by default
          ("POST", "/api/students/{student_id}/enrollment-requests"): 201,
          ("POST", "/api/auth/logout"): 204, ("POST", "/api/admin/users/{user_id}/revoke-sessions"): 204,
          ("POST", "/api/auth/login"): 200, ("POST", "/api/admin/users"): 201,
          ("POST", "/api/admin/students/{student_id}/account"): 201, ("POST", "/api/courses"): 201}
BODIES[("POST", "/api/auth/register")] = {"name": "R", "email": "r@example.edu", "age": 20,
                                          "preferred_content": "Videos", "password": "Register-Pass-123"}
LAST = [("POST", "/api/auth/logout")]                         # ends the session the loop is using


def test_every_route_works_and_is_documented(ml_client, monkeypatch):
    monkeypatch.setenv("ASSISTANT_PROVIDER", "rules")
    schema = ml_client.get("/openapi.json").json()
    routes = [(m.upper(), p) for p, ops in schema["paths"].items() for m in ops]
    assert len(routes) >= 30

    # Fixture data: a student enrolled in PY101 (quiz 1 belongs to PY101).
    sid = ml_client.post("/api/students", json={"name": "Owner", "email": "owner@example.edu", "age": 25,
                                                "preferred_content": "Videos"}).json()["id"]
    py101 = next(c["id"] for c in ml_client.get("/api/courses", params={"search": "PY101"}).json()["items"]
                 if c["code"] == "PY101")
    enrollment = ml_client.post(f"/api/students/{sid}/enrollments", json={"course_id": py101}).json()
    quiz_id = ml_client.get(f"/api/courses/{py101}").json()["quizzes"][0]["id"]
    made = ml_client.post("/api/admin/users", json={"name": "Revoke Me", "email": "revoke.me@example.edu", "age": 22,
                                                    "preferred_content": "Videos", "password": "Granite-Pasture-4821"}).json()
    unused = ml_client.post("/api/courses", json={**BODIES[("POST", "/api/courses")], "code": "COV-DEL"}).json()["id"]
    # enrolment requests: one to approve, one to reject, one for the student to withdraw, one free course to request
    free = {c["code"]: c["id"] for c in ml_client.get("/api/courses", params={"limit": 100}).json()["items"]
            if not c["prerequisite_codes"] and c["code"] in ("DB101", "WD101")}
    other = ml_client.post("/api/students", json={"name": "Requester", "email": "requester@example.edu", "age": 25,
                                                  "preferred_content": "Videos"}).json()["id"]
    pending = lambda student, course: ml_client.post(  # noqa: E731
        f"/api/students/{student}/enrollment-requests", json={"course_id": course}).json()["id"]
    approve_id, reject_id, cancel_id = pending(other, free["DB101"]), pending(other, free["WD101"]), pending(sid, free["WD101"])
    per_route = {("POST", "/api/admin/enrollment-requests/{request_id}/approve"): {"request_id": approve_id},
                 ("POST", "/api/admin/enrollment-requests/{request_id}/reject"): {"request_id": reject_id},
                 ("DELETE", "/api/students/{student_id}/enrollment-requests/{request_id}"): {"request_id": cancel_id}}
    ids = {"student_id": sid, "user_id": made["id"], "unused_course_id": unused, "course_id": py101, "enrollment_id": enrollment["id"], "quiz_id": quiz_id,
           "lesson_id": ml_client.get(f"/api/courses/{py101}").json()["lessons"][0]["id"]}

    def shape(p: str) -> str:
        return re.sub(r"{\w*}", "{}", p.split("?")[0])

    docs_text = (ROOT / "docs" / "API.md").read_text(encoding="utf-8")
    documented_paths = {shape(p) for p in re.findall(r"`(/api/[^`\s]*)`", docs_text)}
    deletes, last = [], []
    for method, path in routes:
        if (method, path) in LAST:
            last.append((method, path))
            continue
        if method == "DELETE":
            deletes.append(path)          # run last so the student still exists
            continue
        url = re.sub(r"{(\w+)}", lambda m: str({**ids, **per_route.get((method, path), {})}[m.group(1)]), path)
        body = BODIES.get((method, path))
        if (method, path) == ("POST", "/api/students/{student_id}/enrollment-requests"):
            body = {"course_id": free["DB101"]}
        if (method, path) == ("POST", "/api/auth/register"):          # a separate client: keep this admin session
            from fastapi.testclient import TestClient
            response = TestClient(ml_client.app).post(url, json=body)
            assert response.status_code == 201 and shape(path) in documented_paths, response.text
            continue
        if (method, path) == ("POST", "/api/students/{student_id}/enrollments"):
            body = {"course_id": next(c["id"] for c in ml_client.get("/api/courses", params={"search": "ST101"}).json()["items"])}
        response = ml_client.request(method, url, json=body)
        if path == "/api/auth/login" and response.status_code == 200:      # a new session has a new CSRF token
            ml_client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        expected = EXPECT.get((method, path)) or SUCCESS.get(method, (200, 201))
        assert response.status_code in (expected if isinstance(expected, tuple) else (expected,)), \
            f"{method} {path} -> {response.status_code}: {response.text[:200]}"
        assert shape(path) in documented_paths, f"{method} {path} missing from docs/API.md"

    for path in sorted(deletes, key=lambda p: p == "/api/students/{student_id}"):   # the student goes last
        url = re.sub(r"{(\w+)}", lambda m: str({**ids, **per_route.get(("DELETE", path), {})}[
            "unused_course_id" if path == "/api/courses/{course_id}" else m.group(1)]), path)
        assert ml_client.delete(url).status_code == 204, path
    for method, path in last:
        assert shape(path) in documented_paths, f"{method} {path} missing from docs/API.md"
        assert ml_client.request(method, path).status_code == 204
        assert ml_client.get("/api/auth/me").status_code == 401        # the session really is gone
