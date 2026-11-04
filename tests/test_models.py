import json

import numpy as np
import pytest

from conftest import new_student
from ml import config
from ml.adaptive_level import AdaptiveLearningSystem
from ml.evaluation import ModelEvaluation
from ml.learning_style import METRICS_FILE, LearningStyleClassification
from ml.peer_recommender import RecommendationAlgorithm
from ml.schema import LEARNING_STYLES, ValidationError


# ------------------------------------------------------------ learning style
def test_no_train_test_leakage(trained, workdirs):
    metrics = json.loads((workdirs["reports"] / METRICS_FILE).read_text())
    test_ids = set(metrics["test_student_ids"])
    assert len(test_ids) == metrics["n_test"] == 20
    assert metrics["n_train"] + metrics["n_test"] == len(trained)

    # The scaler inside the saved pipeline must be fitted on TRAIN rows only.
    model = LearningStyleClassification().load_models().model
    scaler = model.named_steps["preprocessing"].named_transformers_["numeric"]
    train = trained[~trained["StudentID"].isin(test_ids)]
    assert np.allclose(scaler.mean_[0], train["Age"].mean())
    assert not np.allclose(scaler.mean_[0], trained["Age"].mean())


def test_metrics_are_reported_with_baseline(trained, workdirs):
    metrics = json.loads((workdirs["reports"] / METRICS_FILE).read_text())
    for key in ("cv_accuracy_mean", "baseline_cv_accuracy", "test_accuracy",
                "baseline_test_accuracy", "chance_accuracy", "beats_baseline"):
        assert key in metrics
    seg = metrics["segmentation"]
    assert 2 <= seg["n_clusters"] <= 8
    assert sum(p["size"] for p in seg["profiles"]) == len(trained)


def test_classifier_works_after_restart(trained):
    fresh = LearningStyleClassification()          # nothing in memory
    style = fresh.classify_new_student(new_student().drop(columns=["LearningStyle"]))
    assert style in LEARNING_STYLES
    result = fresh.predict(new_student())[0]
    assert abs(sum(result["probabilities"].values()) - 1) < 1e-6
    assert isinstance(result["cluster"], int)


def test_classifier_rejects_invalid_student(trained):
    with pytest.raises(ValidationError):
        LearningStyleClassification().classify_new_student(new_student(Progress=-1))


# ---------------------------------------------------------- peer recommender
def test_peers_exclude_self_and_return_exactly_n(trained):
    recommender = RecommendationAlgorithm()
    for i in (0, 10, 50):
        student = trained.iloc[[i]]
        peers = recommender.find_similar_students(student, n_recommendations=5)
        assert len(peers) == 5
        assert int(student["StudentID"].iloc[0]) not in [p["StudentID"] for p in peers]
        sims = [p["similarity"] for p in peers]
        assert sims == sorted(sims, reverse=True)


def test_peers_are_in_original_units(trained):
    peers = RecommendationAlgorithm().find_similar_students(new_student(), 5)
    assert all(0 <= p["Progress"] <= 1 and 0 <= p["AverageScore"] <= 100 for p in peers)


def test_content_suggestion_shares_sum_to_one(trained):
    rec = RecommendationAlgorithm()
    suggestion = rec.suggest_content(rec.find_similar_students(new_student(), 5))
    assert abs(sum(s["share"] for s in suggestion) - 1) < 0.01


def test_peer_input_validation(trained):
    rec = RecommendationAlgorithm()
    with pytest.raises(ValidationError):
        rec.find_similar_students(new_student(), n_recommendations=0)
    with pytest.raises(ValidationError):
        rec.find_similar_students(new_student().drop(columns=["LearningStyle"]))


# ------------------------------------------------------------ adaptive level
def test_single_student_is_not_always_advanced(trained):
    """The old rank(pct=True) code gave level 2 to every single student."""
    system = AdaptiveLearningSystem()
    weak = system.assess(new_student(Progress=0.05, AverageScore=61))[0]
    strong = system.assess(new_student(Progress=0.95, AverageScore=99))[0]
    assert weak["level"] == 0 and strong["level"] == 2
    assert system.predict(new_student(Progress=0.05, AverageScore=61)).startswith("Beginner")


def test_adaptive_policy_reloads(trained):
    assert AdaptiveLearningSystem().load().reference["Progress"].size == len(trained)


# ---------------------------------------------------------------- evaluation
def test_evaluation_report(trained, workdirs):
    report = ModelEvaluation().run_all()
    cls = report["learning_style_classification"]
    assert cls["train_test_overlap"] == 0
    assert cls["n_test"] == 20
    peers = report["peer_recommender"]
    assert peers["query_student_returned_as_own_peer"] == 0
    adaptive = report["adaptive_level_policy"]
    assert adaptive["monotonic"] is True
    assert adaptive["agreement_with_original_labels"] >= 0.95
    assert (workdirs["reports"] / "evaluation_report.json").exists()


def test_evaluation_fails_clearly_without_models(workdirs, clean_data):
    with pytest.raises(FileNotFoundError):
        ModelEvaluation().evaluate_classification()
