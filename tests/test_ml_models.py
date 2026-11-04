"""Unit tests for the Phase 5 ML modules on small, controlled datasets."""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from ml import bandit, knowledge_tracing, recsys, style_model
from ml.knowledge_tracing import BKTModel
from ml.learner_state import LearnerState, replay, zone_reward
from ml.stats import paired_bootstrap

T0 = datetime(2026, 1, 1)


# ------------------------------------------------------------------- recsys
def catalogue():
    rows = [
        (1, "A1", "Python basics", "python variables loops", "Python", 1, "Videos", ["python"], []),
        (2, "A2", "Python functions", "python functions lists", "Python", 1, "Articles", ["functions"], [1]),
        (3, "B1", "Statistics intro", "mean median variance", "Stats", 1, "Videos", ["mean"], []),
        (4, "B2", "Probability", "probability bayes", "Stats", 2, "Podcasts", ["bayes"], [3]),
        (5, "C1", "HTML basics", "html css layout", "Web", 1, "Podcasts", ["html"], []),
    ]
    return pd.DataFrame(rows, columns=["id", "code", "title", "description", "topic", "level", "content_format",
                                       "skills", "prerequisite_ids"])


def interactions():
    rows = []
    # Many learners go A1 -> A2 ; others B1 -> B2.
    for s in range(1, 21):
        first, second = (1, 2) if s <= 12 else (3, 4)
        rows.append((s, first, "completed", 5, T0))
        rows.append((s, second, "active", None, T0 + timedelta(days=5)))
    return pd.DataFrame(rows, columns=["student_id", "course_id", "status", "rating", "enrolled_at"])


def test_collaborative_learns_co_enrolment():
    model = recsys.CourseRecommender(neighbours=4).fit(catalogue(), interactions())
    history = pd.DataFrame([(1, "completed", 5, T0)], columns=["course_id", "status", "rating", "enrolled_at"])
    top = model.recommend(history, None, method="collaborative", n=1)[0]
    assert top["code"] == "A2"
    assert "Learners who took Python basics also took this course" in top["reasons"]


def test_recommendations_respect_prerequisites_and_history():
    model = recsys.CourseRecommender().fit(catalogue(), interactions())
    history = pd.DataFrame([(1, "completed", 4, T0)], columns=["course_id", "status", "rating", "enrolled_at"])
    codes = [r["code"] for r in model.recommend(history, "Videos", n=10)]
    assert "A1" not in codes            # already taken
    assert "B2" not in codes            # locked: needs B1
    assert set(codes) == {"A2", "B1", "C1"}


def test_content_based_uses_preferred_format_for_cold_start():
    model = recsys.CourseRecommender().fit(catalogue(), interactions())
    empty = pd.DataFrame(columns=["course_id", "status", "rating", "enrolled_at"])
    top = model.recommend(empty, "Podcasts", method="content", n=1)[0]
    assert top["code"] == "C1" and "preferred format" in top["reasons"][0]


def test_recsys_evaluation_structure_and_random_baseline():
    students = pd.DataFrame({"id": range(1, 21), "preferred_content": "Videos"})
    report = recsys.evaluate(catalogue(), interactions(), students, k=2)
    unlocked = report["protocols"]["unlocked_courses"]
    assert report["students_test"] + report["students_tuning"] == 20
    assert unlocked["methods"]["collaborative"]["hit_rate_at_k"] == 1.0   # co-enrolment is perfectly learnable
    assert 0 < unlocked["methods"]["random"]["ndcg_at_k"] < 1
    assert report["tuned_params"]["alpha"] in (0.0, 0.25, 0.5, 0.75, 1.0)


# ---------------------------------------------------------------------- BKT
def simulate_bkt(params, students=60, steps=6, skills=3, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for s in range(students):
        for k in range(skills):
            known = rng.random() < params["p_init"]
            for t in range(steps):
                p = (1 - params["p_slip"]) if known else params["p_guess"]
                rows.append((s, f"skill{k}", T0 + timedelta(days=t), int(rng.random() < p)))
                known = known or rng.random() < params["p_learn"]
    return pd.DataFrame(rows, columns=["student_id", "skill", "attempted_at", "correct"])


def test_bkt_fit_recovers_parameters_roughly():
    truth = {"p_init": 0.3, "p_learn": 0.2, "p_slip": 0.08, "p_guess": 0.2}
    model = BKTModel().fit(simulate_bkt(truth, students=150))
    assert abs(model.p_init - truth["p_init"]) <= 0.2
    assert abs(model.p_learn - truth["p_learn"]) <= 0.15
    assert model.p_guess < 1 - model.p_slip


def test_bkt_mastery_moves_with_evidence():
    model = BKTModel(p_init=0.4, p_learn=0.1, p_slip=0.1, p_guess=0.2)
    right = pd.DataFrame([(1, "x", T0 + timedelta(days=i), 1) for i in range(3)],
                         columns=["student_id", "skill", "attempted_at", "correct"])
    wrong = right.assign(correct=0)
    assert model.mastery(right)["x"]["mastery"] > 0.9
    assert model.mastery(wrong)["x"]["mastery"] < 0.4


def test_bkt_beats_global_baseline_on_bkt_generated_data():
    data = simulate_bkt({"p_init": 0.2, "p_learn": 0.3, "p_slip": 0.05, "p_guess": 0.15}, students=120)
    report = knowledge_tracing.evaluate(data)
    assert report["results"]["bkt"]["auc"] > report["results"]["baseline_global_accuracy"]["auc"]
    assert report["results"]["bkt"]["log_loss"] < report["results"]["baseline_global_accuracy"]["log_loss"]


# ------------------------------------------------------------------- bandit
def test_linucb_learns_context_dependent_best_arm():
    rng = np.random.default_rng(1)
    agent = bandit.LinUCB(n_features=2, alpha=0.3)
    for _ in range(3000):
        skill = rng.random()
        x = np.array([1.0, skill])
        arm = int(rng.choice(bandit.ARMS))
        # Weak learners succeed on level 1, strong learners on level 3.
        p = {1: 1 - skill, 2: 0.5, 3: skill}[arm]
        agent.update(x, arm, float(rng.random() < p))
    assert agent.choose(np.array([1.0, 0.05]), explore=False) == 1
    assert agent.choose(np.array([1.0, 0.95]), explore=False) == 3


def test_zone_reward():
    assert zone_reward(59.9) == 0 and zone_reward(60) == 1 and zone_reward(89.9) == 1 and zone_reward(90) == 0


# --------------------------------------------------------- learner state
def attempts_frame():
    rows = [(1, 1, 10, 1, "Python", 1, "Videos", ["python"], 50.0, T0),
            (2, 1, 11, 2, "Python", 1, "Articles", ["functions"], 100.0, T0 + timedelta(days=3)),
            (3, 1, 10, 1, "Python", 1, "Videos", ["python"], 75.0, T0 + timedelta(days=6))]
    return pd.DataFrame(rows, columns=["attempt_id", "student_id", "quiz_id", "course_id", "topic", "level",
                                       "content_format", "skills", "score", "attempted_at"])


def test_replay_has_no_look_ahead():
    answers = {1: [("python", 0), ("python", 1)], 2: [("functions", 1)], 3: [("python", 1)]}
    rows = replay(attempts_frame(), answers, {1: "Videos"}, BKTModel()).sort_values("attempted_at")
    first, second, third = rows.to_dict("records")
    assert first["prior_attempts"] == 0 and np.isnan(first["prior_mean"])
    assert second["prior_mean"] == 50.0 and second["prior_last"] == 50.0
    assert third["prior_mean"] == 75.0 and third["is_retake"] == 1
    assert first["format_match"] == 1 and second["format_match"] == 0
    assert [r["reward"] for r in (first, second, third)] == [0, 0, 1]


def test_learner_state_context_shape():
    state = LearnerState(BKTModel(), "Videos")
    assert state.context().shape == (5,)
    state.update({"quiz_id": 1, "topic": "x", "level": 1, "content_format": "Videos", "skills": ["a"]}, 80, [("a", 1)])
    assert state.mastery["a"] > BKTModel().p_init


# --------------------------------------------------------------------- style
def test_style_model_flags_unlearnable_labels_as_unreliable():
    rng = np.random.default_rng(0)
    n = 80
    features = pd.DataFrame({
        "age": rng.integers(18, 40, n), "daily_goal_minutes": rng.uniform(20, 120, n),
        "preferred_content": rng.choice(["Videos", "Articles"], n), "avg_quiz_score": rng.uniform(50, 100, n),
        "completion_rate": rng.uniform(0, 1, n), "completed_courses": rng.integers(0, 8, n),
        **{c: rng.dirichlet(np.ones(4), n)[:, i] for i, c in enumerate(style_model.SHARE_COLUMNS)},
        "learning_style": rng.choice(["Visual", "Auditory"], n),       # independent of features
    })
    report = style_model.evaluate(features)
    assert report["reliable"] is False


def test_style_model_detects_learnable_signal():
    rng = np.random.default_rng(0)
    n = 120
    share_videos = rng.uniform(0, 1, n)
    features = pd.DataFrame({
        "age": rng.integers(18, 40, n), "daily_goal_minutes": rng.uniform(20, 120, n),
        "preferred_content": "Videos", "avg_quiz_score": rng.uniform(50, 100, n),
        "completion_rate": rng.uniform(0, 1, n), "completed_courses": rng.integers(0, 8, n),
        "share_articles": 1 - share_videos, "share_podcasts": 0.0, "share_quizzes": 0.0, "share_videos": share_videos,
        "learning_style": np.where(share_videos > 0.5, "Visual", "Reading/Writing"),
    })
    report = style_model.evaluate(features)
    assert report["reliable"] is True and report["cv_accuracy_mean"] > 0.9


# --------------------------------------------------------------------- stats
def test_paired_bootstrap():
    better = paired_bootstrap(np.ones(50) * 0.8, np.ones(50) * 0.5 + np.linspace(-0.05, 0.05, 50), higher_is_better=True)
    assert better["significant"] and better["improvement"] == pytest.approx(0.3, abs=1e-6)
    same = paired_bootstrap(np.linspace(0, 1, 50), np.linspace(0, 1, 50)[::-1], higher_is_better=True)
    assert not same["significant"]
    lower_loss = paired_bootstrap(np.full(30, 0.2), np.full(30, 0.4), higher_is_better=False)
    assert lower_loss["significant"]
