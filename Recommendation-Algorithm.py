
import os
import pandas as pd
import joblib

from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.neighbors import NearestNeighbors


class RecommendationAlgorithm:

    def __init__(self):
        self.model = NearestNeighbors(
            metric="cosine",
            algorithm="brute"
        )
        self.feature_pipeline = None
        self.student_data = None

    def load_data(self, filepath):
        return pd.read_csv(filepath)

    def preprocess_data(self, data):
        return data.dropna().copy()

    def fit(self, data):
        self.student_data = data.copy()

        features = data.drop(
            columns=["StudentID", "avg_performance"],
            errors="ignore"
        )

        numeric_columns = features.select_dtypes(
            include="number"
        ).columns.tolist()

        categorical_columns = features.select_dtypes(
            exclude="number"
        ).columns.tolist()

        self.feature_pipeline = ColumnTransformer([
            ("numeric", StandardScaler(), numeric_columns),
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore"),
                categorical_columns
            )
        ])

        transformed_features = self.feature_pipeline.fit_transform(
            features
        )

        self.model.fit(transformed_features)

        os.makedirs("models", exist_ok=True)

        joblib.dump(
            self.model,
            "models/recommendation_model.pkl"
        )

        joblib.dump(
            self.feature_pipeline,
            "models/recommendation_pipeline.pkl"
        )

        self.student_data.to_csv(
            "models/recommendation_students.csv",
            index=False
        )

        print("Recommendation model trained successfully!")

    def recommend_learning_paths(
        self,
        student_data,
        n_recommendations=5
    ):
        self.model = joblib.load(
            "models/recommendation_model.pkl"
        )

        self.feature_pipeline = joblib.load(
            "models/recommendation_pipeline.pkl"
        )

        self.student_data = pd.read_csv(
            "models/recommendation_students.csv"
        )

        features = student_data.drop(
            columns=["StudentID", "avg_performance"],
            errors="ignore"
        )

        transformed_student = self.feature_pipeline.transform(
            features
        )

        count = min(
            n_recommendations + 1,
            len(self.student_data)
        )

        distances, indices = self.model.kneighbors(
            transformed_student,
            n_neighbors=count
        )

        recommendations = []

        for index in indices[0]:
            student = self.student_data.iloc[index]

            recommendations.append({
                "StudentID": int(student["StudentID"]),
                "LearningStyle": student["LearningStyle"],
                "PreferredContent": student["PreferredContent"],
                "Progress": round(float(student["Progress"]), 3),
                "AverageScore": round(float(student["AverageScore"]), 3)
            })

        return recommendations


if __name__ == "__main__":

    data_filepath = "data/processed/preprocessed_student_data.csv"

    recommender = RecommendationAlgorithm()

    data = recommender.load_data(data_filepath)
    data = recommender.preprocess_data(data)

    recommender.fit(data)

    # Use the first student as a demonstration.
    new_student_data = data.iloc[[0]].copy()

    recommended_paths = recommender.recommend_learning_paths(
        new_student_data,
        n_recommendations=5
    )

    print("\nRecommended Learning Resources")
    print("--------------------------------")

    for recommendation in recommended_paths:
        print(recommendation)
