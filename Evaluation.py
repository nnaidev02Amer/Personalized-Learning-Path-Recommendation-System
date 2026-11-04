
import os
import numpy as np
import pandas as pd
import joblib

from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
)


class ModelEvaluation:

    def evaluate_classification(self, data):
        print("\n1. LEARNING STYLE CLASSIFICATION")
        print("--------------------------------")

        X = data.drop(
            columns=["StudentID", "LearningStyle", "avg_performance"],
            errors="ignore"
        )

        y = data["LearningStyle"]

        X_train, X_test, y_train, y_test = train_test_split(
            X,
            y,
            test_size=0.2,
            random_state=42,
            stratify=y
        )

        model = joblib.load("models/decision_tree_model.pkl")
        pipeline = joblib.load("models/feature_pipeline.pkl")

        X_test = pipeline.transform(X_test)
        predictions = model.predict(X_test)

        print("Accuracy:", round(accuracy_score(y_test, predictions), 4))
        print("Precision:", round(
            precision_score(y_test, predictions, average="weighted", zero_division=0), 4
        ))
        print("Recall:", round(
            recall_score(y_test, predictions, average="weighted", zero_division=0), 4
        ))
        print("F1 Score:", round(
            f1_score(y_test, predictions, average="weighted", zero_division=0), 4
        ))

    def evaluate_recommendations(self, data):
        print("\n2. RECOMMENDATION SYSTEM")
        print("-----------------------")

        model = joblib.load("models/recommendation_model.pkl")
        pipeline = joblib.load("models/recommendation_pipeline.pkl")

        features = data.drop(
            columns=["StudentID", "avg_performance"],
            errors="ignore"
        )

        transformed = pipeline.transform(features)

        distances, indices = model.kneighbors(
            transformed,
            n_neighbors=2
        )

        nearest_distances = []

        for i, row_indices in enumerate(indices):
            for j, index in enumerate(row_indices):
                if data.iloc[index]["StudentID"] != data.iloc[i]["StudentID"]:
                    nearest_distances.append(distances[i][j])
                    break

        if nearest_distances:
            print("Students checked:", len(nearest_distances))
            print(
                "Average distance to nearest similar student:",
                round(float(np.mean(nearest_distances)), 4)
            )

        print("Recommendation model loaded and tested successfully.")
        print("Note: Distance is a similarity measure, not an accuracy score.")

    
    def evaluate_adaptive_system(self, data):
        print("\n3. ADAPTIVE LEARNING SYSTEM")
        print("---------------------------")

        model_path = "models/adaptive_learning_model.pkl"

        if not os.path.exists(model_path):
            print("Adaptive learning model not found.")
            return

        model = joblib.load(model_path)

        print("Adaptive model loaded successfully!")
        print("Model type:", type(model).__name__)

        print("Note: Prediction accuracy cannot be calculated without")
        print("real student feedback or known correct action labels.")



if __name__ == "__main__":

    data_filepath = "data/processed/preprocessed_student_data.csv"

    data = pd.read_csv(data_filepath)

    evaluator = ModelEvaluation()

    evaluator.evaluate_classification(data)
    evaluator.evaluate_recommendations(data)
    evaluator.evaluate_adaptive_system(data)

    print("\n--------------------------------")
    print("PROJECT EVALUATION COMPLETED!")
    print("--------------------------------")
