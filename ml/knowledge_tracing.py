"""Bayesian Knowledge Tracing (Corbett & Anderson, 1994) for skill mastery.

Each skill is a hidden binary state (known / not known). Per observation:

    P(correct)      = L * (1 - slip) + (1 - L) * guess
    posterior L     = L(1-slip)/P(correct)            if correct
                    = L*slip/(1 - P(correct))          if wrong
    next L          = posterior + (1 - posterior) * learn

Parameters (p_init, p_learn, p_slip, p_guess) are shared across skills and fitted
by maximum likelihood over a grid -- per-skill fits are not identifiable with the
2-8 observations a student typically has per skill. Observations are the
per-question answers of quiz attempts (``observations`` DataFrame with columns
student_id, skill, attempted_at, correct).

Evaluation: students are split 70/30; parameters are fitted on the training
students; on the test students every answer is predicted from that student's
*earlier* answers only. AUC, log-loss and Brier score are compared with three
baselines: global accuracy, per-skill accuracy (from training students) and the
student's running accuracy so far.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

GRID = {
    "p_init": np.round(np.arange(0.1, 0.95, 0.1), 2),
    "p_learn": np.array([0.02, 0.05, 0.1, 0.2, 0.3, 0.45]),
    "p_slip": np.array([0.03, 0.08, 0.15, 0.25]),
    "p_guess": np.array([0.1, 0.2, 0.3, 0.4]),
}
MASTERY_THRESHOLD = 0.6


def _sequences(obs: pd.DataFrame):
    """Yield (student, skill, correctness array) in time order."""
    obs = obs.sort_values(["student_id", "skill", "attempted_at"], kind="mergesort")
    for (sid, skill), g in obs.groupby(["student_id", "skill"], sort=False):
        yield sid, skill, g["correct"].to_numpy(dtype=float)


def _forward(params: np.ndarray, sequences) -> tuple[np.ndarray, np.ndarray]:
    """Vectorised over parameter sets. params: (P, 4). Returns predictions (P, N) and outcomes (N)."""
    p_init, p_learn, p_slip, p_guess = params.T
    preds, outcomes = [], []
    for seq in sequences:
        L = p_init.copy()
        for c in seq:
            p = L * (1 - p_slip) + (1 - L) * p_guess
            preds.append(p)
            outcomes.append(c)
            post = np.where(c == 1, L * (1 - p_slip) / p, L * p_slip / (1 - p))
            L = post + (1 - post) * p_learn
    return np.array(preds).T, np.array(outcomes)


@dataclass
class BKTModel:
    p_init: float = 0.5
    p_learn: float = 0.1
    p_slip: float = 0.1
    p_guess: float = 0.25

    @property
    def params(self) -> dict:
        return {k: float(getattr(self, k)) for k in ("p_init", "p_learn", "p_slip", "p_guess")}

    def fit(self, observations: pd.DataFrame) -> "BKTModel":
        grid = np.array(list(itertools.product(*GRID.values())))
        grid = grid[grid[:, 3] < 1 - grid[:, 2]]          # guess < 1 - slip (identifiability)
        seqs = [s for _, _, s in _sequences(observations)]
        if not seqs:
            return self
        preds, y = _forward(grid, seqs)
        preds = np.clip(preds, 1e-6, 1 - 1e-6)
        ll = (y * np.log(preds) + (1 - y) * np.log(1 - preds)).sum(axis=1)
        self.p_init, self.p_learn, self.p_slip, self.p_guess = grid[int(np.argmax(ll))]
        self.n_observations = int(len(y))
        return self

    def _vec(self) -> np.ndarray:
        return np.array([[self.p_init, self.p_learn, self.p_slip, self.p_guess]])

    def mastery(self, observations: pd.DataFrame) -> dict[str, dict]:
        """Posterior P(known) per skill after all of one student's observations."""
        out = {}
        for _, skill, seq in _sequences(observations):
            L = self.p_init
            for c in seq:
                p = L * (1 - self.p_slip) + (1 - L) * self.p_guess
                post = L * (1 - self.p_slip) / p if c == 1 else L * self.p_slip / (1 - p)
                L = post + (1 - post) * self.p_learn
            out[skill] = {"mastery": round(float(L), 4), "observations": int(len(seq)),
                          "accuracy": round(float(seq.mean()), 4)}
        return out

    def predict_sequences(self, observations: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        preds, y = _forward(self._vec(), [s for _, _, s in _sequences(observations)])
        return preds[0], y


def _scores(y, p) -> dict:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return {"auc": round(float(roc_auc_score(y, p)), 4) if len(set(y)) > 1 else None,
            "log_loss": round(float(log_loss(y, p, labels=[0, 1])), 4),
            "brier": round(float(brier_score_loss(y, p)), 4)}


def evaluate(observations: pd.DataFrame, *, test_fraction: float = 0.3, random_state: int = 42) -> dict:
    students = np.array(sorted(observations["student_id"].unique()))
    rng = np.random.default_rng(random_state)
    test_ids = set(rng.choice(students, size=max(1, int(len(students) * test_fraction)), replace=False).tolist())
    train = observations[~observations["student_id"].isin(test_ids)]
    test = observations[observations["student_id"].isin(test_ids)]

    model = BKTModel().fit(train)
    p_bkt, y = model.predict_sequences(test)

    # Baselines, aligned with the same (student, skill, time) ordering.
    ordered = test.sort_values(["student_id", "skill", "attempted_at"], kind="mergesort")
    global_acc = float(train["correct"].mean())
    skill_acc = train.groupby("skill")["correct"].mean()
    p_skill = ordered["skill"].map(skill_acc).fillna(global_acc).to_numpy()
    # Student's running accuracy over *earlier* answers (any skill), by time.
    by_time = test.sort_values(["student_id", "attempted_at"], kind="mergesort").copy()
    prior_correct = by_time.groupby("student_id")["correct"].cumsum() - by_time["correct"]
    prior_n = by_time.groupby("student_id").cumcount()
    by_time["p_student"] = np.where(prior_n > 0, (prior_correct + global_acc) / (prior_n + 1), global_acc)
    p_student = by_time.loc[ordered.index, "p_student"].to_numpy()

    results = {
        "bkt": _scores(y, p_bkt),
        "baseline_global_accuracy": _scores(y, np.full_like(y, global_acc)),
        "baseline_skill_accuracy": _scores(y, p_skill),
        "baseline_student_running_accuracy": _scores(y, p_student),
    }
    best_baseline = min((k for k in results if k.startswith("baseline")), key=lambda k: results[k]["log_loss"])
    preds = {"bkt": p_bkt, "baseline_global_accuracy": np.full_like(y, global_acc),
             "baseline_skill_accuracy": p_skill, "baseline_student_running_accuracy": p_student}

    def pointwise_ll(p):
        p = np.clip(p, 1e-6, 1 - 1e-6)
        return -(y * np.log(p) + (1 - y) * np.log(1 - p))

    from ml.stats import paired_bootstrap
    comparison = paired_bootstrap(pointwise_ll(preds["bkt"]), pointwise_ll(preds[best_baseline]),
                                  higher_is_better=False)
    return {
        "protocol": "70/30 student split; BKT params fitted on training students; each test answer "
                    "predicted from that student's earlier answers only",
        "params": model.params, "train_observations": int(len(train)), "test_observations": int(len(y)),
        "test_students": len(test_ids), "results": results, "best_baseline": best_baseline,
        "vs_best_baseline_log_loss": comparison,
        "beats_best_baseline": comparison["significant"],
    }
