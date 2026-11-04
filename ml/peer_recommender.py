"""Peer-similarity recommender (the original ``Recommendation-Algorithm.py``).

What it does: finds the students most similar to a given student (cosine k-NN
on scaled profile features + learning style) and derives a content-format
suggestion from what those peers prefer. It recommends *peers / content
formats*, not courses -- course-level recommendation (content-based,
collaborative and hybrid filtering) needs a course catalogue and enrolment
data, which the original dataset does not contain; that is added in Phase 3.

Fixes compared to the original script:
* The query student is no longer returned as its own top recommendation.
* Exactly ``n_recommendations`` results are returned (was n + 1).
* Values are reported in original units (was standardised, e.g. Progress -0.96).
* Each result carries a similarity score; inputs are validated.
* Models are loaded from disk only when not already fitted.
"""

from __future__ import annotations

from collections import defaultdict

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from ml import config
from ml.schema import (CATEGORICAL_FEATURES, NUMERIC_FEATURES, PROFILE_FEATURES,
                       ValidationError, validate_students)

FEATURES = PROFILE_FEATURES + ["LearningStyle"]


class RecommendationAlgorithm:

    def __init__(self):
        self.model = NearestNeighbors(metric="cosine", algorithm="brute")
        self.feature_pipeline: ColumnTransformer | None = None
        self.student_data: pd.DataFrame | None = None

    def load_data(self, filepath) -> pd.DataFrame:
        return pd.read_csv(filepath)

    def preprocess_data(self, data: pd.DataFrame) -> pd.DataFrame:
        return validate_students(data.dropna(), require_id=True, require_style=True)

    def fit(self, data: pd.DataFrame, save: bool = True) -> "RecommendationAlgorithm":
        self.student_data = data.reset_index(drop=True).copy()
        self.feature_pipeline = ColumnTransformer([
            ("numeric", StandardScaler(), NUMERIC_FEATURES),
            ("categorical", OneHotEncoder(handle_unknown="ignore"),
             CATEGORICAL_FEATURES + ["LearningStyle"]),
        ])
        self.model.fit(self.feature_pipeline.fit_transform(self.student_data[FEATURES]))
        if save:
            out = config.models_dir()
            joblib.dump(self.model, out / "recommendation_model.pkl")
            joblib.dump(self.feature_pipeline, out / "recommendation_pipeline.pkl")
            self.student_data.to_csv(out / "recommendation_students.csv", index=False)
        return self

    def load(self) -> "RecommendationAlgorithm":
        out = config.models_dir()
        self.model = joblib.load(out / "recommendation_model.pkl")
        self.feature_pipeline = joblib.load(out / "recommendation_pipeline.pkl")
        self.student_data = pd.read_csv(out / "recommendation_students.csv")
        return self

    def find_similar_students(self, student_data: pd.DataFrame,
                              n_recommendations: int = 5) -> list[dict]:
        """Top-n most similar *other* students for the first row of input."""
        if not isinstance(n_recommendations, int) or n_recommendations < 1:
            raise ValidationError("n_recommendations must be a positive integer")
        if self.feature_pipeline is None:
            self.load()

        student = validate_students(student_data.iloc[[0]], require_style=True)
        own_id = int(student["StudentID"].iloc[0]) if "StudentID" in student else None

        # Ask for one extra neighbour in case the student is in the reference set.
        n_neighbors = min(n_recommendations + 1, len(self.student_data))
        distances, indices = self.model.kneighbors(
            self.feature_pipeline.transform(student[FEATURES]), n_neighbors=n_neighbors)

        results = []
        for distance, index in zip(distances[0], indices[0]):
            peer = self.student_data.iloc[index]
            if own_id is not None and int(peer["StudentID"]) == own_id:
                continue
            results.append({
                "StudentID": int(peer["StudentID"]),
                "similarity": round(1.0 - float(distance), 4),
                "LearningStyle": str(peer["LearningStyle"]),
                "PreferredContent": str(peer["PreferredContent"]),
                "Progress": round(float(peer["Progress"]), 3),
                "AverageScore": round(float(peer["AverageScore"]), 2),
            })
        return results[:n_recommendations]

    # Original method name, kept for backward compatibility.
    def recommend_learning_paths(self, student_data, n_recommendations=5):
        return self.find_similar_students(student_data, n_recommendations)

    @staticmethod
    def suggest_content(peers: list[dict]) -> list[dict]:
        """Rank content formats by similarity-weighted peer preference."""
        weights: dict[str, float] = defaultdict(float)
        for peer in peers:
            weights[peer["PreferredContent"]] += max(peer["similarity"], 0.0)
        total = sum(weights.values()) or 1.0
        return [{"content_type": c, "share": round(w / total, 3)}
                for c, w in sorted(weights.items(), key=lambda kv: -kv[1])]


def run(data_path=None, demo_student_index: int = 0):
    data_path = data_path or config.processed_dir() / config.CLEAN_CSV
    recommender = RecommendationAlgorithm()
    data = recommender.preprocess_data(recommender.load_data(data_path))
    recommender.fit(data)
    peers = recommender.find_similar_students(data.iloc[[demo_student_index]], 5)
    return recommender, data.iloc[demo_student_index], peers
