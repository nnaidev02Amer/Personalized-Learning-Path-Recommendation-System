"""Student performance prediction: expected score (0-100) on the next quiz.

Model: gradient-boosted trees on point-in-time features from
``learner_state.FEATURES`` (prior scores, topic history, course level, format
match, BKT mastery of the quiz's skills, retake flag).

Evaluation: chronological split -- the BKT parameters and the regressor are fitted
only on attempts before the cut-off; the last 20% of attempts (by time) are
predicted. Baselines: training mean score, and the student's own prior mean
(falling back to the training mean for a first attempt).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline

from ml.knowledge_tracing import BKTModel
from ml.learner_state import FEATURES, replay


def make_model(random_state: int = 42) -> Pipeline:
    return Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("gbr", GradientBoostingRegressor(n_estimators=200, max_depth=3, learning_rate=0.05,
                                          subsample=0.8, random_state=random_state)),
    ])


def _metrics(y, p) -> dict:
    return {"mae": round(float(mean_absolute_error(y, p)), 3),
            "rmse": round(float(np.sqrt(mean_squared_error(y, p))), 3),
            "r2": round(float(r2_score(y, p)), 4)}


def evaluate(attempts: pd.DataFrame, answers: dict, observations: pd.DataFrame, preferred: dict,
             *, test_fraction: float = 0.2) -> dict:
    ordered = attempts.sort_values("attempted_at", kind="mergesort")
    cutoff = ordered["attempted_at"].iloc[int(len(ordered) * (1 - test_fraction))]
    bkt = BKTModel().fit(observations[observations["attempted_at"] < cutoff])
    rows = replay(attempts, answers, preferred, bkt)
    train, test = rows[rows["attempted_at"] < cutoff], rows[rows["attempted_at"] >= cutoff]

    model = make_model().fit(train[FEATURES], train["score"])
    p_model = np.clip(model.predict(test[FEATURES]), 0, 100)
    train_mean = float(train["score"].mean())
    p_student = test["prior_mean"].fillna(train_mean).to_numpy()
    y = test["score"].to_numpy()

    results = {"gradient_boosting": _metrics(y, p_model),
               "baseline_train_mean": _metrics(y, np.full_like(y, train_mean)),
               "baseline_student_prior_mean": _metrics(y, p_student)}
    importances = dict(zip(FEATURES, model.named_steps["gbr"].feature_importances_.round(4).tolist()))
    from ml.stats import paired_bootstrap
    baseline_preds = {"baseline_train_mean": np.full_like(y, train_mean), "baseline_student_prior_mean": p_student}
    best = min(baseline_preds, key=lambda b: results[b]["mae"])
    comparison = paired_bootstrap(np.abs(y - p_model), np.abs(y - baseline_preds[best]), higher_is_better=False)
    return {
        "protocol": "chronological split; BKT + regressor fitted on attempts before the cut-off; "
                    "last 20% of attempts predicted",
        "cutoff": str(cutoff), "train_attempts": int(len(train)), "test_attempts": int(len(test)),
        "results": results, "best_baseline": best,
        "vs_best_baseline_abs_error": comparison,
        "beats_baseline": comparison["significant"],
        "feature_importance": dict(sorted(importances.items(), key=lambda kv: -kv[1])),
    }
