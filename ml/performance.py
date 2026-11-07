"""Student performance prediction: expected score (0-100) on the next quiz.

Model: **ability-anchored gradient boosting.**

1. *Ability anchor.* Every earlier answer the learner gave is evidence of their
   ability. The ability estimate is the empirical-Bayes (Beta-Binomial) posterior
   mean accuracy ``(correct + mu*kappa) / (answers + kappa)``: with few answers it
   stays near the population mean ``mu``, with many it follows the learner. The
   shrinkage strength ``kappa`` is *estimated from the training data* (the value
   with the lowest squared error of the anchor, the criterion for which a
   posterior mean is optimal), not hand-set.
2. *Residual.* A small, heavily regularised gradient-boosted tree model learns
   what ability does not explain (course level, retake, format match, BKT
   mastery, topic-specific form, trend). Monotonic constraints encode domain
   logic -- more mastery / a retake / a better topic record can never *lower* the
   prediction -- so the model cannot respond to history in the wrong direction.

Why not plain gradient boosting on the raw features (the previous model)? On this
data only ~1 training row in 750 comes from a learner who had answered 2+ quizzes
poorly; trees cannot learn behaviour for a region they have never seen, and the
fitted response to a learner's own prior score was not even monotonic. Anchoring
on a statistically sound ability estimate makes the prediction follow the
learner's record by construction, and the booster only has to model the small
remainder.

Evaluation: chronological split -- the BKT parameters and the regressor are fitted
only on attempts before the cut-off; the last 20% of attempts (by time) are
predicted. Baselines: training mean score, and the student's own prior mean
(falling back to the training mean for a first attempt). The ability anchor alone
is reported as well, so the value added by the booster is visible.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from ml.knowledge_tracing import BKTModel
from ml.learner_state import FEATURES, replay

KAPPAS = (0.5, 1, 2, 4, 8, 16, 32, 64, 128)         # candidate shrinkage strengths (pseudo-answers)
MIN_ROWS_FOR_RESIDUAL = 60
# residual features and the direction in which each may move the prediction (0 = unconstrained)
RESIDUAL_FEATURES = {"level": 0, "is_retake": 1, "format_match": 0, "quiz_skill_mastery": 1,
                     "overall_mastery": 1, "prior_trend": 0, "topic_gap": 1}


class AbilityAnchoredRegressor(BaseEstimator, RegressorMixin):
    """Score = 100 x shrunk ability + monotone boosted residual. Input: ``learner_state.FEATURES`` columns."""

    def __init__(self, random_state: int = 42, use_residual: bool = True):
        self.random_state = random_state
        self.use_residual = use_residual

    # ---- ability anchor
    def ability(self, X: pd.DataFrame) -> np.ndarray:
        """Posterior mean accuracy (0-100) from the learner's earlier answers."""
        n = X["prior_answers"].to_numpy(dtype=float)
        c = X["prior_correct"].to_numpy(dtype=float)
        return 100.0 * (c + self.population_accuracy_ * self.kappa_) / (n + self.kappa_)

    def _residual_frame(self, X: pd.DataFrame) -> pd.DataFrame:
        r = X[[c for c in RESIDUAL_FEATURES if c != "topic_gap"]].copy()
        r["topic_gap"] = (X["topic_prior_mean"] - X["prior_mean"]).fillna(0.0)   # 0 when topic history is unknown
        return r[list(RESIDUAL_FEATURES)]

    def fit(self, X: pd.DataFrame, y) -> "AbilityAnchoredRegressor":
        y = np.asarray(y, dtype=float)
        self.population_accuracy_ = float(y.mean() / 100.0)
        errors = []
        for kappa in KAPPAS:
            self.kappa_ = float(kappa)
            errors.append(float(np.mean((y - self.ability(X)) ** 2)))   # squared error <=> posterior-mean estimate
        self.kappa_ = float(KAPPAS[int(np.argmin(errors))])
        self.residual_ = None
        if self.use_residual and len(X) >= MIN_ROWS_FOR_RESIDUAL:
            self.residual_ = HistGradientBoostingRegressor(
                max_depth=2, max_iter=60, learning_rate=0.05, min_samples_leaf=40, l2_regularization=5.0,
                monotonic_cst=list(RESIDUAL_FEATURES.values()), random_state=self.random_state,
            ).fit(self._residual_frame(X), y - self.ability(X))
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        pred = self.ability(X)
        if self.residual_ is not None:
            pred = pred + self.residual_.predict(self._residual_frame(X))
        return np.clip(pred, 0.0, 100.0)


def make_model(random_state: int = 42) -> AbilityAnchoredRegressor:
    return AbilityAnchoredRegressor(random_state=random_state)


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
    ability_only = AbilityAnchoredRegressor(use_residual=False).fit(train[FEATURES], train["score"])
    p_model = model.predict(test[FEATURES])
    train_mean = float(train["score"].mean())
    p_student = test["prior_mean"].fillna(train_mean).to_numpy()
    y = test["score"].to_numpy()

    results = {"gradient_boosting": _metrics(y, p_model),
               "baseline_train_mean": _metrics(y, np.full_like(y, train_mean)),
               "baseline_student_prior_mean": _metrics(y, p_student),
               "ability_only": _metrics(y, ability_only.predict(test[FEATURES]))}
    from ml.stats import paired_bootstrap
    baseline_preds = {"baseline_train_mean": np.full_like(y, train_mean), "baseline_student_prior_mean": p_student}
    best = min(baseline_preds, key=lambda b: results[b]["mae"])
    comparison = paired_bootstrap(np.abs(y - p_model), np.abs(y - baseline_preds[best]), higher_is_better=False)
    vs_ability = paired_bootstrap(np.abs(y - p_model), np.abs(y - ability_only.predict(test[FEATURES])),
                                  higher_is_better=False)
    imp = permutation_importance(model, test[FEATURES], y, scoring="neg_mean_absolute_error",
                                 n_repeats=5, random_state=42).importances_mean
    imp = np.clip(imp, 0, None)
    importances = dict(zip(FEATURES, (imp / imp.sum() if imp.sum() > 0 else imp).round(4).tolist()))
    return {
        "protocol": "chronological split; BKT + regressor fitted on attempts before the cut-off; "
                    "last 20% of attempts predicted",
        "model": "ability-anchored gradient boosting: empirical-Bayes ability from earlier answers + "
                 "monotone boosted residual",
        "ability_prior_strength": model.kappa_, "population_accuracy": round(model.population_accuracy_, 4),
        "cutoff": str(cutoff), "train_attempts": int(len(train)), "test_attempts": int(len(test)),
        "results": results, "best_baseline": best,
        "vs_best_baseline_abs_error": comparison,
        "beats_baseline": comparison["significant"],
        "vs_ability_only_abs_error": vs_ability,
        "feature_importance": dict(sorted(importances.items(), key=lambda kv: -kv[1])),
    }
