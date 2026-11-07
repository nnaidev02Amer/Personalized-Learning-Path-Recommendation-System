"""End-to-end regression tests for QA BUG-04 (BKT) and BUG-05 (score prediction).

Runs through the real API on the ``ml_client`` fixture: a temporary copy of a freshly seeded template
database with models trained on it. The live database is never touched.
"""

from api_helpers import course_id


def make_student(client, tag):
    return client.post("/api/students", json={"name": tag, "email": f"{tag}@example.edu", "age": 22,
                                              "preferred_content": "Videos"}).json()["id"]


def enrol_py101(client, sid):
    cid = course_id(client, "PY101")
    client.post(f"/api/students/{sid}/enrollments", json={"course_id": cid})
    return client.get(f"/api/courses/{cid}").json()["quizzes"][0]["id"]


def answer_key(client, quiz_id):
    """Learn the answer key from a throw-away student's feedback (the quiz endpoint never exposes it)."""
    sid = make_student(client, "key.finder")
    enrol_py101(client, sid)
    feedback = client.post(f"/api/students/{sid}/quizzes/{quiz_id}/attempts",
                           json={"answers": [0, 0, 0, 0]}).json()["feedback"]
    return [f["correct_option"] for f in feedback]


def attempt(client, sid, quiz_id, answers, times=1):
    for _ in range(times):
        assert client.post(f"/api/students/{sid}/quizzes/{quiz_id}/attempts", json={"answers": answers}).status_code == 201


def test_bug04_three_failed_attempts_are_gaps_not_mastery(ml_client):
    sid = make_student(ml_client, "weak.skills")
    quiz = enrol_py101(ml_client, sid)
    attempt(ml_client, sid, quiz, [0, 0, 0, 0], times=3)
    body = ml_client.get(f"/api/students/{sid}/skills").json()
    skills = {s["skill"]: s for s in body["skills"]}
    assert skills and all(s["accuracy"] == 0 for s in skills.values())
    assert not any(s["mastered"] for s in skills.values()), skills          # was True for 2 of 3 skills
    assert {g["skill"] for g in body["gaps"]} >= set(skills)
    assert all(s["mastery"] < body["threshold"] for s in skills.values())


def test_bug04_a_good_record_is_still_recognised_as_mastery(ml_client):
    sid = make_student(ml_client, "strong.skills")
    quiz = enrol_py101(ml_client, sid)
    key = answer_key(ml_client, quiz)
    attempt(ml_client, sid, quiz, key, times=2)
    body = ml_client.get(f"/api/students/{sid}/skills").json()
    assert body["skills"] and all(s["mastered"] for s in body["skills"])
    assert body["gaps"] == []


def test_bug04_mastery_ranks_stronger_record_above_weaker(ml_client):
    weak, strong = make_student(ml_client, "rank.weak"), make_student(ml_client, "rank.strong")
    quiz = enrol_py101(ml_client, weak)
    enrol_py101(ml_client, strong)
    key = answer_key(ml_client, quiz)
    attempt(ml_client, weak, quiz, [0, 0, 0, 0], times=2)
    attempt(ml_client, strong, quiz, key, times=2)
    mean = lambda sid: sum(s["mastery"] for s in ml_client.get(f"/api/students/{sid}/skills").json()["skills"])  # noqa: E731
    assert mean(strong) > mean(weak) + 0.3


def test_bug05_prediction_follows_the_quiz_history(ml_client):
    weak, strong = make_student(ml_client, "pred.weak"), make_student(ml_client, "pred.strong")
    quiz = enrol_py101(ml_client, weak)
    enrol_py101(ml_client, strong)
    key = answer_key(ml_client, quiz)
    attempt(ml_client, weak, quiz, [0, 0, 0, 0], times=3)               # 0% three times
    attempt(ml_client, strong, quiz, key, times=3)                       # 100% three times

    def prediction(sid):
        items = ml_client.get(f"/api/students/{sid}/predictions").json()["items"]
        assert len(items) == 1
        return items[0]

    w, s = prediction(weak), prediction(strong)
    pass_mark = 60
    assert w["predicted_score"] < pass_mark, w                           # was 82.9-90.2 "likely"
    assert w["pass_probability_hint"] != "likely"
    assert s["predicted_score"] > w["predicted_score"] + 25, (w, s)
    assert s["pass_probability_hint"] != "at risk"
    assert w["previous_attempts"] == s["previous_attempts"] == 3


def test_bug05_each_failed_attempt_lowers_the_prediction(ml_client):
    sid = make_student(ml_client, "pred.decline")
    quiz = enrol_py101(ml_client, sid)
    values = []
    for _ in range(3):
        attempt(ml_client, sid, quiz, [0, 0, 0, 0])
        values.append(ml_client.get(f"/api/students/{sid}/predictions").json()["items"][0]["predicted_score"])
    assert values[0] > values[1] > values[2], values


def test_evaluation_report_keeps_the_keys_the_frontend_reads(ml_client):
    report = ml_client.get("/api/ml/evaluation").json()
    pp, kt = report["performance_prediction"], report["knowledge_tracing"]
    assert {"gradient_boosting", "baseline_student_prior_mean", "baseline_train_mean"} <= set(pp["results"])
    assert "feature_importance" in pp and "vs_best_baseline_abs_error" in pp and "cutoff" in pp
    assert {"p_init", "p_learn", "p_slip", "p_guess"} <= set(kt["params"])
    body = ml_client.get("/api/students/7/skills").json()           # read-only view of a seeded student's skills
    assert 0 < body["params"]["p_init"] < 1 and body["threshold"] == 0.6
