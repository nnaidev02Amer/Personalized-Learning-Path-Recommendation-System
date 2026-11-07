"""Bayesian Knowledge Tracing (Corbett & Anderson, 1994) for skill mastery, with an
individualised prior.

Each skill is a hidden binary state (known / not known). Per observation:

    P(correct)      = L * (1 - slip) + (1 - L) * guess
    posterior L     = L(1-slip)/P(correct)            if correct
                    = L*slip/(1 - P(correct))          if wrong
    next L          = posterior + (1 - posterior) * learn

**Individualised prior.** Classic BKT starts every learner at the same ``p_init``.
On real and simulated course data most of the variance in correctness is a
*persistent learner trait* (accuracy across students ranges from ~0.6 to ~0.95),
so a shared prior ignores the strongest signal there is. Here the initial
knowledge of a skill the learner has not been tested on yet is derived from how
the learner answered *other* skills, shrunk toward the population::

    acc   = (n/(n+m)) * (c/n) + (m/(n+m)) * population_accuracy      # c of n earlier answers
    L0    = (acc - guess) / (1 - slip - guess)                       # clipped to (0, 1)

``m`` (``prior_strength``) is fitted like the other parameters. ``m = inf``
reproduces classic BKT, so the model is a strict generalisation. With no earlier
answers ``L0 == p_init`` exactly.

**Fitting.** Parameters are shared across skills (per-skill fits are not
identifiable from the 2-8 answers a student has per skill) and are fitted by
maximum likelihood over a grid whose bounds follow the standard BKT
degeneracy constraints (guess <= 0.3, slip <= 0.25, learn <= 0.3). The
likelihood surface is nearly flat, and unconstrained fits drift to a corner of
the grid (e.g. learn = 0.45) which lets mastery "recover" after any number of
wrong answers. Among all parameter sets whose log-likelihood is within the 95%
likelihood-ratio tolerance (1.92) of the maximum, the **most conservative** one
is chosen: the largest ``prior_strength`` (least individualisation; classic BKT
if it is statistically indistinguishable), then the smallest ``p_learn``.

Observations are the per-question answers of quiz attempts (``observations``
DataFrame with columns student_id, skill, attempted_at, correct).

**Evaluation.** Students are split 70/30; parameters are fitted on the training
students; on the test students every answer is predicted from that student's
*earlier* answers only (any skill, in time order). AUC, log-loss and Brier score
are compared with three baselines: global accuracy, per-skill accuracy (from
training students) and the student's running accuracy so far.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

GRID = {
    "p_init": np.round(np.arange(0.1, 0.95, 0.1), 2),
    "p_learn": np.array([0.02, 0.05, 0.1, 0.2, 0.3]),
    "p_slip": np.array([0.03, 0.08, 0.15, 0.25]),
    "p_guess": np.array([0.1, 0.2, 0.25, 0.3]),
    "prior_strength": np.array([2.0, 4.0, 8.0, 16.0, 32.0, np.inf]),
}
LR_TOLERANCE = 1.92          # chi-square(1, 95%) / 2: log-likelihood units indistinguishable from the maximum
MASTERY_THRESHOLD = 0.6
_PARAM_NAMES = ("p_init", "p_learn", "p_slip", "p_guess", "prior_strength")


def _initial_knowledge(p_init, p_slip, p_guess, strength, n_correct, n_total):
    """Initial P(known) for a skill the learner has not been tested on, from n_total earlier answers.

    Works on scalars or on parameter arrays (vectorised grid search).
    """
    population_acc = p_init * (1 - p_slip) + (1 - p_init) * p_guess
    weight = n_total / (n_total + strength) if n_total > 0 else 0.0
    own_acc = n_correct / n_total if n_total > 0 else 0.0
    acc = weight * own_acc + (1 - weight) * population_acc
    return np.clip((acc - p_guess) / (1 - p_slip - p_guess), 0.01, 0.99)


def _timelines(obs: pd.DataFrame):
    """Yield (student, skills, correctness) per student in time order (stable within an attempt)."""
    obs = obs.sort_values(["student_id", "attempted_at"], kind="mergesort")
    for sid, g in obs.groupby("student_id", sort=False):
        yield sid, g["skill"].tolist(), g["correct"].to_numpy(dtype=float)


def _sweep(params: np.ndarray, timelines, *, keep_predictions: bool):
    """Run the learner timelines through every parameter set at once.

    params: (P, 5). Returns (log_likelihood (P,), predictions (P, N) or None, outcomes (N,)).
    """
    p_init, p_learn, p_slip, p_guess, strength = params.T
    ll = np.zeros(len(params))
    preds, outcomes = [], []
    for _sid, skills, correct in timelines:
        L: dict[str, np.ndarray] = {}
        c = n = 0
        for skill, y in zip(skills, correct):
            if skill not in L:
                L[skill] = _initial_knowledge(p_init, p_slip, p_guess, strength, c, n)
            Lk = L[skill]
            p = np.clip(Lk * (1 - p_slip) + (1 - Lk) * p_guess, 1e-6, 1 - 1e-6)
            ll += np.log(p) if y == 1 else np.log(1 - p)
            if keep_predictions:
                preds.append(p)
            outcomes.append(y)
            post = Lk * (1 - p_slip) / p if y == 1 else Lk * p_slip / (1 - p)
            L[skill] = post + (1 - post) * p_learn
            c += int(y)
            n += 1
    return ll, (np.array(preds).T if keep_predictions else None), np.array(outcomes)


@dataclass
class BKTModel:
    p_init: float = 0.5
    p_learn: float = 0.1
    p_slip: float = 0.1
    p_guess: float = 0.25
    prior_strength: float = float("inf")      # inf == classic BKT (no individualised prior)

    @property
    def params(self) -> dict:
        out = {k: float(getattr(self, k)) for k in _PARAM_NAMES[:4]}
        out["prior_strength"] = None if np.isinf(self.prior_strength) else float(self.prior_strength)
        return out

    # -------------------------------------------------------------- fitting
    def fit(self, observations: pd.DataFrame) -> "BKTModel":
        timelines = list(_timelines(observations))
        if not timelines:
            return self
        grid = np.array(list(itertools.product(*GRID.values())))
        grid = grid[grid[:, 3] < 1 - grid[:, 2]]          # guess < 1 - slip (identifiability)
        ll, _, y = _sweep(grid, timelines, keep_predictions=False)
        candidates = np.where(ll >= ll.max() - LR_TOLERANCE)[0]
        # most conservative among the statistically indistinguishable: least individualised, slowest learner
        order = np.lexsort((-ll[candidates], grid[candidates, 1], -grid[candidates, 4]))
        best = grid[candidates[order[0]]]
        self.p_init, self.p_learn, self.p_slip, self.p_guess, self.prior_strength = (float(v) for v in best)
        self.n_observations = int(len(y))
        self.n_equivalent_fits = int(len(candidates))
        return self

    # ------------------------------------------------------------ inference
    def initial_knowledge(self, n_correct: int = 0, n_total: int = 0) -> float:
        """P(known) before a skill's first observation, given the learner's earlier answers on other skills."""
        return float(_initial_knowledge(self.p_init, self.p_slip, self.p_guess, self.prior_strength,
                                        n_correct, n_total))

    def update_knowledge(self, L: float, correct) -> float:
        """One BKT step: Bayes update on the answer, then the learning transition."""
        p = L * (1 - self.p_slip) + (1 - L) * self.p_guess
        post = L * (1 - self.p_slip) / p if correct else L * self.p_slip / (1 - p)
        return float(post + (1 - post) * self.p_learn)

    def mastery(self, observations: pd.DataFrame) -> dict[str, dict]:
        """Posterior P(known) per skill after all of one student's observations.

        The prior of each skill uses the learner's answers on all *other* skills.
        """
        obs = observations.sort_values(["student_id", "skill", "attempted_at"], kind="mergesort")
        totals = obs.groupby("skill")["correct"].agg(["sum", "count"])
        all_c, all_n = int(totals["sum"].sum()), int(totals["count"].sum())
        out = {}
        for skill, g in obs.groupby("skill", sort=False):
            seq = g["correct"].to_numpy(dtype=float)
            L = self.initial_knowledge(all_c - int(seq.sum()), all_n - len(seq))
            for c in seq:
                L = self.update_knowledge(L, c)
            out[skill] = {"mastery": round(float(L), 4), "observations": int(len(seq)),
                          "accuracy": round(float(seq.mean()), 4)}
        return out

    def predict_sequences(self, observations: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        """P(correct) for every answer, from that learner's *earlier* answers only. Order: student, time."""
        vec = np.array([[self.p_init, self.p_learn, self.p_slip, self.p_guess, self.prior_strength]])
        _, preds, y = _sweep(vec, list(_timelines(observations)), keep_predictions=True)
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

    # Baselines, aligned with the same (student, time) ordering as the BKT predictions.
    ordered = test.sort_values(["student_id", "attempted_at"], kind="mergesort")
    global_acc = float(train["correct"].mean())
    skill_acc = train.groupby("skill")["correct"].mean()
    p_skill = ordered["skill"].map(skill_acc).fillna(global_acc).to_numpy()
    # Student's running accuracy over *earlier* answers (any skill), by time.
    prior_correct = ordered.groupby("student_id")["correct"].cumsum() - ordered["correct"]
    prior_n = ordered.groupby("student_id").cumcount()
    p_student = np.where(prior_n > 0, (prior_correct + global_acc) / (prior_n + 1), global_acc)

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
                    "predicted from that student's earlier answers (any skill) only",
        "params": model.params, "train_observations": int(len(train)), "test_observations": int(len(y)),
        "test_students": len(test_ids), "results": results, "best_baseline": best_baseline,
        "vs_best_baseline_log_loss": comparison,
        "beats_best_baseline": comparison["significant"],
    }
