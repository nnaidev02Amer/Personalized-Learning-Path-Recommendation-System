def course_id(client, code: str) -> int:
    items = client.get("/api/courses", params={"search": code}).json()["items"]
    return next(c["id"] for c in items if c["code"] == code)


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    body = response.json()["error"]
    assert body["code"] == code and body["message"]
    return body
