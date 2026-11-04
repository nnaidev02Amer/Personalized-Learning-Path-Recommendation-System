"""Every route in the OpenAPI schema is exercised and documented (Phase 6)."""

import re

from ml_helpers import ROOT

# Bodies for write endpoints; ids are filled from a freshly created student/enrolment.
BODIES = {
    ("POST", "/api/students"): {"name": "Cov", "email": "cov@example.edu", "age": 30, "preferred_content": "Videos"},
    ("PATCH", "/api/students/{student_id}"): {"age": 31},
    ("POST", "/api/students/{student_id}/activity"): {"minutes": 15},
    ("POST", "/api/students/{student_id}/enrollments"): None,     # filled with PY101 id
    ("PATCH", "/api/enrollments/{enrollment_id}"): {"status": "active"},
    ("POST", "/api/students/{student_id}/quizzes/{quiz_id}/attempts"): {"answers": [1, 2, 1, 2]},
    ("POST", "/api/students/{student_id}/assistant"): {"message": "How am I doing?"},
}
SUCCESS = {"GET": 200, "PATCH": 200, "DELETE": 204}


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
    ids = {"student_id": sid, "course_id": py101, "enrollment_id": enrollment["id"], "quiz_id": quiz_id,
           "lesson_id": ml_client.get(f"/api/courses/{py101}").json()["lessons"][0]["id"]}

    def shape(p: str) -> str:
        return re.sub(r"{\w*}", "{}", p.split("?")[0])

    docs_text = (ROOT / "docs" / "API.md").read_text(encoding="utf-8")
    documented_paths = {shape(p) for p in re.findall(r"`(/api/[^`\s]*)`", docs_text)}
    deletes = []
    for method, path in routes:
        if method == "DELETE":
            deletes.append(path)          # run last so the student still exists
            continue
        url = re.sub(r"{(\w+)}", lambda m: str(ids[m.group(1)]), path)
        body = BODIES.get((method, path))
        if (method, path) == ("POST", "/api/students/{student_id}/enrollments"):
            body = {"course_id": next(c["id"] for c in ml_client.get("/api/courses", params={"search": "ST101"}).json()["items"])}
        response = ml_client.request(method, url, json=body)
        expected = SUCCESS.get(method, (200, 201))
        assert response.status_code in (expected if isinstance(expected, tuple) else (expected,)), \
            f"{method} {path} -> {response.status_code}: {response.text[:200]}"
        assert shape(path) in documented_paths, f"{method} {path} missing from docs/API.md"

    for path in deletes:
        url = re.sub(r"{(\w+)}", lambda m: str(ids[m.group(1)]), path)
        assert ml_client.delete(url).status_code == 204
