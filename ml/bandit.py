"""Adaptive difficulty with a LinUCB contextual bandit (Li et al., 2010).

Arms: course difficulty level 1 (Beginner), 2 (Intermediate), 3 (Advanced).
Context: learner state before the quiz (see ``learner_state.CONTEXT_NAMES``).
Reward: 1 when the quiz score lands in the "productive challenge" zone
[60, 90) -- passed, but not trivially easy -- else 0.

The bandit is warm-started offline from historical quiz attempts and then
updated online after every quiz a student submits through the API.

Evaluation (chronological 80/20 split):
* reward-model quality on held-out attempts (Brier score, accuracy) versus a
  context-free per-arm average reward;
* replay estimate of policy value: mean reward over held-out events where the
  greedy policy agrees with the logged difficulty, versus the logged average.
  Historical difficulty was not chosen at random, so this estimate is biased
  and reported as indicative only.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss

ARMS = (1, 2, 3)
ARM_NAMES = {1: "Beginner", 2: "Intermediate", 3: "Advanced"}


class LinUCB:
    def __init__(self, n_features: int, alpha: float = 0.5, ridge: float = 1.0):
        self.alpha = alpha
        self.A = {a: ridge * np.eye(n_features) for a in ARMS}
        self.b = {a: np.zeros(n_features) for a in ARMS}
        self.counts = {a: 0 for a in ARMS}

    def update(self, x: np.ndarray, arm: int, reward: float) -> None:
        self.A[arm] += np.outer(x, x)
        self.b[arm] += reward * x
        self.counts[arm] += 1

    def fit(self, contexts, arms, rewards) -> "LinUCB":
        for x, a, r in zip(contexts, arms, rewards):
            self.update(np.asarray(x, float), int(a), float(r))
        return self

    def arm_estimates(self, x: np.ndarray) -> dict[int, dict]:
        out = {}
        for a in ARMS:
            A_inv = np.linalg.inv(self.A[a])
            theta = A_inv @ self.b[a]
            mean = float(theta @ x)
            bonus = float(self.alpha * np.sqrt(x @ A_inv @ x))
            out[a] = {"expected_reward": float(np.clip(mean, 0, 1)), "uncertainty": bonus,
                      "ucb": mean + bonus, "observations": self.counts[a]}
        return out

    def choose(self, x: np.ndarray, explore: bool = True) -> int:
        est = self.arm_estimates(x)
        key = "ucb" if explore else "expected_reward"
        return max(ARMS, key=lambda a: (est[a][key], -a))


def evaluate(rows: pd.DataFrame, *, test_fraction: float = 0.2, alpha: float = 0.5) -> dict:
    rows = rows.sort_values("attempted_at", kind="mergesort").reset_index(drop=True)
    cut = int(len(rows) * (1 - test_fraction))
    train, test = rows.iloc[:cut], rows.iloc[cut:]
    d = len(train["context"].iloc[0])
    bandit = LinUCB(d, alpha=alpha).fit(train["context"], train["arm"], train["reward"])

    y = test["reward"].to_numpy()
    p_model = np.array([bandit.arm_estimates(np.asarray(x))[a]["expected_reward"]
                        for x, a in zip(test["context"], test["arm"])])
    arm_mean = train.groupby("arm")["reward"].mean()
    p_arm = test["arm"].map(arm_mean).fillna(train["reward"].mean()).to_numpy()
    p_global = np.full(len(test), train["reward"].mean())

    greedy = np.array([bandit.choose(np.asarray(x), explore=False) for x in test["context"]])
    agree = greedy == test["arm"].to_numpy()

    def score(p):
        return {"brier": round(float(brier_score_loss(y, np.clip(p, 0, 1))), 4),
                "accuracy": round(float(np.mean((p >= 0.5) == (y == 1))), 4)}

    results = {"linucb": score(p_model), "baseline_arm_mean": score(p_arm), "baseline_global_mean": score(p_global)}
    from ml.stats import paired_bootstrap
    comparison = paired_bootstrap((np.clip(p_model, 0, 1) - y) ** 2, (p_arm - y) ** 2, higher_is_better=False)
    return {
        "protocol": "chronological 80/20 split of quiz attempts; reward = score in [60, 90)",
        "train_events": int(len(train)), "test_events": int(len(test)),
        "reward_rate_test": round(float(y.mean()), 4),
        "reward_model": results,
        "vs_arm_mean_brier": comparison,
        "beats_baseline": comparison["significant"],
        "replay": {
            "matched_events": int(agree.sum()),
            "policy_reward_on_matched": round(float(y[agree].mean()), 4) if agree.any() else None,
            "logged_reward": round(float(y.mean()), 4),
            "note": "biased estimate - historical difficulty was not randomised",
        },
        "arm_counts_train": {ARM_NAMES[a]: int(n) for a, n in train["arm"].value_counts().sort_index().items()},
    }
