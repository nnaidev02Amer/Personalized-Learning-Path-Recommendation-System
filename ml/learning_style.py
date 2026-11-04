"""Learning-style classification (K-Means segmentation + Decision Tree).

Fixes compared to the original script:
* Scaling/encoding lives *inside* one sklearn Pipeline that is fitted on the
  training split only (no test-set leakage, no double scaling).
* The number of K-Means clusters is chosen by silhouette score instead of a
  hard-coded 4, and the cluster profiles are saved instead of being discarded.
* Decision Tree depth is tuned with cross-validation on the training split.
* Every score is reported next to a majority-class baseline, and the held-out
  StudentIDs are saved so ``evaluation.py`` re-uses the exact same test set.
* ``load_models()`` is restored, so ``classify_new_student`` works after a
  restart; new inputs are validated.
"""

from __future__ import annotations

import json

import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.metrics import (accuracy_score, classification_report, f1_score,
                             silhouette_score)
from sklearn.model_selection import (GridSearchCV, StratifiedKFold,
                                     cross_val_score, train_test_split)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier

from ml import config
from ml.schema import (CATEGORICAL_FEATURES, NUMERIC_FEATURES, PROFILE_FEATURES,
                       validate_students)

PIPELINE_FILE = "learning_style_pipeline.pkl"
SEGMENTATION_FILE = "kmeans_pipeline.pkl"
METRICS_FILE = "learning_style_metrics.json"


def build_preprocessor() -> ColumnTransformer:
    return ColumnTransformer([
        ("numeric", StandardScaler(), NUMERIC_FEATURES),
        ("categorical", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
    ])


class LearningStyleClassification:

    def __init__(self, n_clusters: int | None = None, k_range=range(2, 9),
                 random_state: int = config.RANDOM_STATE):
        self.n_clusters = n_clusters          # None -> choose by silhouette
        self.k_range = k_range
        self.random_state = random_state
        self.segmentation: Pipeline | None = None
        self.model: Pipeline | None = None
        self.label_encoder = LabelEncoder()
        self.cluster_report: dict = {}
        self.metrics: dict = {}

    # ----------------------------------------------------------------- data
    def load_data(self, filepath) -> pd.DataFrame:
        return pd.read_csv(filepath)

    def preprocess_data(self, data: pd.DataFrame) -> pd.DataFrame:
        return validate_students(data.dropna(), require_id=True, require_style=True)

    # ----------------------------------------------------------- clustering
    def cluster_students(self, data: pd.DataFrame) -> pd.DataFrame:
        """Unsupervised segmentation of students on their profile features."""
        features = data[PROFILE_FEATURES]
        X = build_preprocessor().fit_transform(features)

        silhouettes = {}
        if self.n_clusters is None:
            for k in self.k_range:
                if k >= len(data):
                    break
                labels = KMeans(k, random_state=self.random_state, n_init=10).fit_predict(X)
                silhouettes[k] = round(float(silhouette_score(X, labels)), 4)
            best_k = max(silhouettes, key=silhouettes.get)
        else:
            best_k = self.n_clusters

        self.segmentation = Pipeline([
            ("preprocessing", build_preprocessor()),
            ("kmeans", KMeans(best_k, random_state=self.random_state, n_init=10)),
        ])
        data = data.copy()
        data["cluster"] = self.segmentation.fit_predict(features)

        profiles = (data.groupby("cluster")[NUMERIC_FEATURES].mean().round(3)
                    .assign(size=data["cluster"].value_counts().sort_index()))
        self.cluster_report = {
            "n_clusters": int(best_k),
            "silhouette_by_k": silhouettes,
            "silhouette": round(float(silhouette_score(
                self.segmentation[:-1].transform(features), data["cluster"])), 4),
            "profiles": profiles.reset_index().to_dict(orient="records"),
            # How well do clusters line up with the labelled learning styles?
            "style_mix_per_cluster": {
                int(k): {str(s): int(n) for s, n in row.items()}
                for k, row in pd.crosstab(data["cluster"], data["LearningStyle"])
                .to_dict(orient="index").items()},
        }
        return data

    # -------------------------------------------------------- classification
    def train_classifier(self, data: pd.DataFrame, test_size: float = 0.2) -> dict:
        X = data[PROFILE_FEATURES]
        y = data["LearningStyle"]
        self.label_encoder.fit(y)

        X_train, X_test, y_train, y_test, id_train, id_test = train_test_split(
            X, y, data["StudentID"], test_size=test_size,
            random_state=self.random_state, stratify=y)

        cv = StratifiedKFold(5, shuffle=True, random_state=self.random_state)
        search = GridSearchCV(
            Pipeline([("preprocessing", build_preprocessor()),
                      ("classifier", DecisionTreeClassifier(random_state=self.random_state))]),
            {"classifier__max_depth": [2, 3, 4, 6, None],
             "classifier__min_samples_leaf": [1, 3, 5]},
            cv=cv, scoring="accuracy")
        search.fit(X_train, y_train)
        self.model = search.best_estimator_

        baseline = DummyClassifier(strategy="most_frequent").fit(X_train, y_train)
        predictions = self.model.predict(X_test)
        baseline_cv = cross_val_score(DummyClassifier(strategy="most_frequent"),
                                      X_train, y_train, cv=cv)

        self.metrics = {
            "model": "DecisionTreeClassifier",
            "best_params": search.best_params_,
            "n_train": len(X_train),
            "n_test": len(X_test),
            "cv_accuracy_mean": round(float(search.best_score_), 4),
            "cv_accuracy_std": round(float(
                search.cv_results_["std_test_score"][search.best_index_]), 4),
            "baseline_cv_accuracy": round(float(baseline_cv.mean()), 4),
            "test_accuracy": round(float(accuracy_score(y_test, predictions)), 4),
            "test_f1_weighted": round(float(f1_score(
                y_test, predictions, average="weighted", zero_division=0)), 4),
            "baseline_test_accuracy": round(float(accuracy_score(
                y_test, baseline.predict(X_test))), 4),
            "chance_accuracy": round(1 / y.nunique(), 4),
            "test_student_ids": sorted(int(i) for i in id_test),
            "classification_report": classification_report(
                y_test, predictions, zero_division=0, output_dict=True),
        }
        self.metrics["beats_baseline"] = (
            self.metrics["test_accuracy"] > self.metrics["baseline_test_accuracy"])
        return self.metrics

    # ----------------------------------------------------------- persistence
    def save_models(self) -> None:
        out = config.models_dir()
        joblib.dump(self.model, out / PIPELINE_FILE)
        joblib.dump(self.segmentation, out / SEGMENTATION_FILE)
        # Original file names, kept so older code that loads them still works.
        joblib.dump(self.model.named_steps["classifier"], out / "decision_tree_model.pkl")
        joblib.dump(self.model.named_steps["preprocessing"], out / "feature_pipeline.pkl")
        joblib.dump(self.segmentation.named_steps["kmeans"], out / "kmeans_model.pkl")
        joblib.dump(self.label_encoder, out / "label_encoder.pkl")

        report = {**self.metrics, "segmentation": self.cluster_report}
        (config.reports_dir() / METRICS_FILE).write_text(json.dumps(report, indent=2, default=_json), encoding="utf-8")

    def load_models(self) -> "LearningStyleClassification":
        out = config.models_dir()
        self.model = joblib.load(out / PIPELINE_FILE)
        self.segmentation = joblib.load(out / SEGMENTATION_FILE)
        self.label_encoder = joblib.load(out / "label_encoder.pkl")
        return self

    # ------------------------------------------------------------- inference
    def classify_new_student(self, student_data: pd.DataFrame) -> str:
        return self.predict(student_data)[0]["learning_style"]

    def predict(self, student_data: pd.DataFrame) -> list[dict]:
        """Predicted style, class probabilities and segment for each row."""
        if self.model is None:
            self.load_models()
        X = validate_students(student_data)[PROFILE_FEATURES]
        probabilities = self.model.predict_proba(X)
        classes = self.model.classes_
        clusters = self.segmentation.predict(X)
        return [{
            "learning_style": str(classes[int(np.argmax(row))]),
            "probabilities": {str(c): round(float(p), 4) for c, p in zip(classes, row)},
            "cluster": int(cluster),
        } for row, cluster in zip(probabilities, clusters)]


def _json(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    return str(value)


def run(data_path=None) -> LearningStyleClassification:
    data_path = data_path or config.processed_dir() / config.CLEAN_CSV
    classifier = LearningStyleClassification()
    data = classifier.preprocess_data(classifier.load_data(data_path))
    clustered = classifier.cluster_students(data)
    classifier.train_classifier(clustered)
    classifier.save_models()
    return classifier
