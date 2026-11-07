def course_id(client, code: str) -> int:
    items = client.get("/api/courses", params={"search": code}).json()["items"]
    return next(c["id"] for c in items if c["code"] == code)


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    body = response.json()["error"]
    assert body["code"] == code and body["message"]
    return body


def enrol_via_approval(client, student_id: int, code: str | None = None, course: int | None = None) -> dict:
    """Enrol ``student_id`` the way the product does: an enrolment request, approved by the administrator.

    ``client`` may be the student or the administrator; returns the resulting enrolment."""
    from conftest import ADMIN_EMAIL, ADMIN_PASSWORD, login
    cid = course if course is not None else course_id(client, code)
    sent = client.post(f"/api/students/{student_id}/enrollment-requests", json={"course_id": cid})
    assert sent.status_code == 201, sent.text
    admin = login(client.app, ADMIN_EMAIL, ADMIN_PASSWORD)
    approved = admin.post(f"/api/admin/enrollment-requests/{sent.json()['id']}/approve")
    assert approved.status_code == 200, approved.text
    return next(e for e in admin.get(f"/api/students/{student_id}/enrollments").json() if e["course"]["id"] == cid)
