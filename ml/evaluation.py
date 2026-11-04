"""Honest evaluation of the student-profile models.

Fixes compared to the original script:
* The classifier is scored on the *exact* held-out StudentIDs saved at
  training time (previously the split was re-created and silently relied on
  the same seed and file).
* Every score is shown next to a baseline, so a number can't look good just
  because it is non-zero.
* The peer recommender gets a real, leakage-free check: can similar peers
  predict a student's preferred content format when that column is hidden?
* The level policy is checked for agreement with the original labelling rule
  and for monotonicity (better progress/score never lowers the level).
"""

from __future__ import annotations

import json

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from ml import config
from ml.adaptive_level import AdaptiveLearningSystem
from ml.learning_style import METRICS_FILE, PIPELINE_FILE
from ml.peer_recommender import RecommendationAlgorithm
from ml.schema import NUMERIC_FEATURES, PROFILE_FEATURES

REPORT_FILE = "evaluation_report.json"


def _r(x) -> float:
    return round(float(x), 4)


class ModelEvaluation:

    def __init__(self, data: pd.DataFrame | None = None):
        self.data = data if data is not None else pd.read_csv(
            config.processed_dir() / config.CLEAN_CSV)
        self.report: dict = {}

    def evaluate_classification(self) -> dict:
        model = joblib.load(config.models_dir() / PIPELINE_FILE)
        saved = json.loads((config.reports_dir() / METRICS_FILE).read_text(encoding="utf-8"))
        test_ids = set(saved["test_student_ids"])

        is_test = self.data["StudentID"].isin(test_ids)
        train, test = self.data[~is_test], self.data[is_test]
        if len(test) != len(test_ids):
            raise RuntimeError("Saved test StudentIDs do not match the data; retrain the classifier.")

        y_true = test["LearningStyle"]
        y_pred = model.predict(test[PROFILE_FEATURES])
        baseline = DummyClassifier(strategy="most_frequent").fit(
            train[PROFILE_FEATURES], train["LearningStyle"]).predict(test[PROFILE_FEATURES])

        result = {
            "n_test": int(len(test)),
            "train_test_overlap": int(len(set(train["StudentID"]) & test_ids)),
            "accuracy": _r(accuracy_score(y_true, y_pred)),
            "precision_weighted": _r(precision_score(y_true, y_pred, average="weighted", zero_division=0)),
            "recall_weighted": _r(recall_score(y_true, y_pred, average="weighted", zero_division=0)),
            "f1_weighted": _r(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
            "baseline_accuracy": _r(accuracy_score(y_true, baseline)),
            "chance_accuracy": _r(1 / self.data["LearningStyle"].nunique()),
            "cv_accuracy_mean": saved["cv_accuracy_mean"],
            "baseline_cv_accuracy": saved["baseline_cv_accuracy"],
            "kmeans_clusters": saved["segmentation"]["n_clusters"],
            "kmeans_silhouette": saved["segmentation"]["silhouette"],
        }
        result["beats_baseline"] = result["accuracy"] > result["baseline_accuracy"]
        self.report["learning_style_classification"] = result
        return result

    def evaluate_recommendations(self, k: int = 5) -> dict:
        recommender = RecommendationAlgorithm().load()
        similarities, self_hits = [], 0
        for i in range(len(self.data)):
            peers = recommender.find_similar_students(self.data.iloc[[i]], k)
            similarities.append(np.mean([p["similarity"] for p in peers]))
            self_hits += any(p["StudentID"] == self.data.iloc[i]["StudentID"] for p in peers)

        # Leakage-free usefulness check: hide PreferredContent and predict it
        # from the k most similar peers (cross-validated).
        features = [c for c in PROFILE_FEATURES if c != "PreferredContent"] + ["LearningStyle"]
        knn = Pipeline([
            ("preprocessing", ColumnTransformer([
                ("numeric", StandardScaler(), NUMERIC_FEATURES),
                ("categorical", OneHotEncoder(handle_unknown="ignore"), ["LearningStyle"]),
            ])),
            ("knn", KNeighborsClassifier(n_neighbors=k, metric="cosine", weights="distance")),
        ])
        X, y = self.data[features], self.data["PreferredContent"]
        cv = StratifiedKFold(5, shuffle=True, random_state=config.RANDOM_STATE)
        peer_acc = cross_val_score(knn, X, y, cv=cv)
        base_acc = cross_val_score(DummyClassifier(strategy="most_frequent"), X, y, cv=cv)

        result = {
            "k": k,
            "students_checked": len(self.data),
            "query_student_returned_as_own_peer": int(self_hits),
            "mean_peer_similarity": _r(np.mean(similarities)),
            "peer_content_prediction_cv_accuracy": _r(peer_acc.mean()),
            "baseline_content_prediction_cv_accuracy": _r(base_acc.mean()),
        }
        result["beats_baseline"] = (result["peer_content_prediction_cv_accuracy"]
                                    > result["baseline_content_prediction_cv_accuracy"])
        self.report["peer_recommender"] = result
        return result

    def evaluate_adaptive_system(self) -> dict:
        system = AdaptiveLearningSystem().load()
        assessed = system.assess(self.data)
        levels = np.array([a["level"] for a in assessed])

        # Original batch labelling rule (percentile ranks within the dataset).
        performance = (self.data["Progress"].rank(pct=True)
                       + self.data["AverageScore"].rank(pct=True)) / 2
        original = pd.cut(performance, [-0.01, 0.33, 0.66, 1.01], labels=[0, 1, 2]).astype(int)

        # Monotonicity: raising progress and score must never lower the level.
        better = self.data.copy()
        better["Progress"] = np.minimum(better["Progress"] + 0.1, 1.0)
        better["AverageScore"] = np.minimum(better["AverageScore"] + 5, 100.0)
        better_levels = np.array([a["level"] for a in system.assess(better)])

        result = {
            "rule": "mean percentile of Progress and AverageScore -> 3 levels",
            "level_distribution": {system.actions[i]: int((levels == i).sum()) for i in range(3)},
            "agreement_with_original_labels": _r((levels == original.to_numpy()).mean()),
            "monotonic": bool((better_levels >= levels).all()),
            "note": "Rule-based policy; accuracy is not applicable. "
                    "Reinforcement learning is evaluated from Phase 3.",
        }
        self.report["adaptive_level_policy"] = result
        return result

    def run_all(self) -> dict:
        self.evaluate_classification()
        self.evaluate_recommendations()
        self.evaluate_adaptive_system()
        self.report["dataset"] = {
            "source": "sample_data.csv",
            "rows": len(self.data),
            "warning": "Features in this dataset are statistically independent of "
                       "LearningStyle (see docs/PHASE1_ANALYSIS.md); no model can be "
                       "expected to beat the baseline on it.",
        }
        (config.reports_dir() / REPORT_FILE).write_text(json.dumps(self.report, indent=2), encoding="utf-8")
        return self.report
