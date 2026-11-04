
import os
import pandas as pd
import joblib

from sklearn.cluster import KMeans
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler, LabelEncoder
from sklearn.pipeline import Pipeline
from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report


class LearningStyleClassification:

    def __init__(self, n_clusters=4):
        self.n_clusters = n_clusters
        self.kmeans = KMeans(
            n_clusters=n_clusters,
            random_state=42,
            n_init=10
        )
        self.decision_tree = None
        self.label_encoder = LabelEncoder()
        self.feature_pipeline = None

    def load_data(self, filepath):
        return pd.read_csv(filepath)

    def preprocess_data(self, data):
        return data.dropna().copy()

    def prepare_features(self, data):
        features = data.drop(
            columns=["StudentID", "LearningStyle", "avg_performance"],
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
            ("categorical", OneHotEncoder(handle_unknown="ignore"), categorical_columns)
        ])

        return self.feature_pipeline.fit_transform(features)

    def cluster_students(self, data):
        features = self.prepare_features(data)

        data = data.copy()
        data["cluster"] = self.kmeans.fit_predict(features)

        return data

    def train_classifier(self, data):
        features = data.drop(
            columns=["StudentID", "LearningStyle", "avg_performance", "cluster"],
            errors="ignore"
        )

        target = data["LearningStyle"]

        self.label_encoder.fit(target)

        X_train, X_test, y_train, y_test = train_test_split(
            features,
            target,
            test_size=0.2,
            random_state=42,
            stratify=target
        )

        numeric_columns = features.select_dtypes(
            include="number"
        ).columns.tolist()

        categorical_columns = features.select_dtypes(
            exclude="number"
        ).columns.tolist()

        self.feature_pipeline = ColumnTransformer([
            ("numeric", StandardScaler(), numeric_columns),
            ("categorical", OneHotEncoder(handle_unknown="ignore"), categorical_columns)
        ])

        X_train = self.feature_pipeline.fit_transform(X_train)
        X_test = self.feature_pipeline.transform(X_test)

        self.decision_tree = DecisionTreeClassifier(random_state=42)
        self.decision_tree.fit(X_train, y_train)

        predictions = self.decision_tree.predict(X_test)

        print("\nDecision Tree Classifier Results")
        print("--------------------------------")
        print("Accuracy:", round(accuracy_score(y_test, predictions), 4))
        print("\nClassification Report:")
        print(classification_report(y_test, predictions, zero_division=0))

    def save_models(self):
        os.makedirs("models", exist_ok=True)

        joblib.dump(self.kmeans, "models/kmeans_model.pkl")
        joblib.dump(self.decision_tree, "models/decision_tree_model.pkl")
        joblib.dump(self.feature_pipeline, "models/feature_pipeline.pkl")
        joblib.dump(self.label_encoder, "models/label_encoder.pkl")

        print("\nModels saved successfully in the models folder.")

    def classify_new_student(self, student_data):
        processed_data = self.feature_pipeline.transform(student_data)
        return self.decision_tree.predict(processed_data)[0]


if __name__ == "__main__":

    data_filepath = "data/processed/preprocessed_student_data.csv"

    classifier = LearningStyleClassification()

    data = classifier.load_data(data_filepath)
    data = classifier.preprocess_data(data)

    clustered_data = classifier.cluster_students(data)

    classifier.train_classifier(clustered_data)

    classifier.save_models()
