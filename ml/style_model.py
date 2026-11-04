"""Learning-style prediction from profile + behaviour stored in the database.

Features per student: age, daily study goal, preferred content format, share of
course study time spent per content format (Videos/Articles/Podcasts/Quizzes),
average quiz score, completion rate and number of completed courses.
Target: the labelled learning style (from sample_data.csv for seeded students).

Model: Decision Tree (as in the original project), depth tuned by an inner CV.
Evaluation: 5-fold stratified *nested* cross-validation versus a majority-class
baseline. The model is flagged ``reliable`` only when its mean CV accuracy beats
the baseline by more than one standard deviation of the fold scores; otherwise
the API reports the prediction together with that warning.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.model_selection import GridSearchCV, StratifiedKFold, cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier

from ml.schema import CONTENT_TYPES

SHARE_COLUMNS = [f"share_{c.lower()}" for c in CONTENT_TYPES]
NUMERIC = ["age", "daily_goal_minutes", "avg_quiz_score", "completion_rate", "completed_courses", *SHARE_COLUMNS]
CATEGORICAL = ["preferred_content"]


def build_features(students: pd.DataFrame, enrollments: pd.DataFrame, attempts: pd.DataFrame,
                   activity: pd.DataFrame, courses: pd.DataFrame) -> pd.DataFrame:
    """students: id, age, daily_goal_minutes, preferred_content, learning_style."""
    df = students.set_index("id")[["age", "daily_goal_minutes", "preferred_content", "learning_style"]].copy()
    fmt = courses.set_index("id")["content_format"]
    act = activity.dropna(subset=["course_id"]).copy()
    act["format"] = act["course_id"].astype(int).map(fmt)
    minutes = act.pivot_table(index="student_id", columns="format", values="minutes", aggfunc="sum", fill_value=0)
    for c in CONTENT_TYPES:
        col = minutes[c] if c in minutes else 0
        df[f"share_{c.lower()}"] = (col / minutes.sum(axis=1)).reindex(df.index) if len(minutes) else np.nan
    df["avg_quiz_score"] = attempts.groupby("student_id")["score"].mean().reindex(df.index)
    status = enrollments.groupby("student_id")["status"]
    df["completed_courses"] = status.apply(lambda s: (s == "completed").sum()).reindex(df.index).fillna(0)
    df["completion_rate"] = status.apply(lambda s: (s == "completed").mean()).reindex(df.index)
    return df


def make_model(random_state: int = 42) -> GridSearchCV:
    from sklearn.impute import SimpleImputer
    pre = ColumnTransformer([
        ("num", Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), NUMERIC),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
    ])
    pipe = Pipeline([("pre", pre), ("tree", DecisionTreeClassifier(random_state=random_state))])
    return GridSearchCV(pipe, {"tree__max_depth": [2, 3, 5], "tree__min_samples_leaf": [1, 5]},
                        cv=StratifiedKFold(3, shuffle=True, random_state=random_state), scoring="accuracy")


def evaluate(features: pd.DataFrame, random_state: int = 42) -> dict:
    data = features.dropna(subset=["learning_style"])
    X, y = data[NUMERIC + CATEGORICAL], data["learning_style"]
    outer = StratifiedKFold(5, shuffle=True, random_state=random_state)
    model_scores = cross_val_score(make_model(random_state), X, y, cv=outer)
    base_scores = cross_val_score(DummyClassifier(strategy="most_frequent"), X, y, cv=outer)
    margin = float(model_scores.mean() - base_scores.mean())
    return {
        "protocol": "5-fold stratified nested CV (inner 3-fold grid search over tree depth)",
        "students": int(len(data)),
        "cv_accuracy_mean": round(float(model_scores.mean()), 4),
        "cv_accuracy_std": round(float(model_scores.std()), 4),
        "baseline_majority_accuracy": round(float(base_scores.mean()), 4),
        "chance_accuracy": round(1 / y.nunique(), 4),
        "reliable": bool(margin > model_scores.std()),
    }


def fit(features: pd.DataFrame, random_state: int = 42):
    data = features.dropna(subset=["learning_style"])
    return make_model(random_state).fit(data[NUMERIC + CATEGORICAL], data["learning_style"]).best_estimator_


def predict(model, features_row: pd.DataFrame) -> dict:
    proba = model.predict_proba(features_row[NUMERIC + CATEGORICAL])[0]
    classes = model.classes_
    return {"predicted_style": str(classes[int(np.argmax(proba))]),
            "probabilities": {str(c): round(float(p), 4) for c, p in zip(classes, proba)}}
