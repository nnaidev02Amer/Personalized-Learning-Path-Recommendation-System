"""Learning-level policy (the original ``Adaptive-Learning-System.py``).

The original script labelled each student with a level computed from the
percentile ranks of ``Progress`` and ``AverageScore``, then trained a
RandomForest to predict that label *from the same two columns* (plus noise
features). That is target leakage: the forest only re-learns a known formula,
and it did so imperfectly (measured 0.77 5-fold CV accuracy on its own label).
Labelling a single new student with ``rank(pct=True)`` also always produced
level 2, because a one-row rank is always 1.0.

This module applies the documented rule directly and correctly:

1. ``fit`` stores the reference distribution of Progress and AverageScore.
2. For any student, each value is converted to a percentile *against that
   reference* (empirical CDF), and the two percentiles are averaged.
3. The performance percentile maps to one of three actions (< 1/3, < 2/3, rest).

It is deterministic, explainable, and works for single new students. The
genuinely adaptive component -- reinforcement learning (Q-learning and a
contextual bandit) driven by quiz outcomes -- is built in Phase 3 on top of
the richer interaction data that the original dataset lacks.
"""

from __future__ import annotations

import joblib
import numpy as np
import pandas as pd

from ml import config
from ml.schema import validate_students

MODEL_FILE = "adaptive_learning_model.pkl"   # original file name kept
SIGNALS = ("Progress", "AverageScore")
THRESHOLDS = (1 / 3, 2 / 3)


class AdaptiveLearningSystem:

    actions = {
        0: "Beginner - Study basic concepts",
        1: "Practice - Solve quizzes and exercises",
        2: "Advanced - Move to advanced topics",
    }

    def __init__(self):
        self.reference: dict[str, np.ndarray] = {}

    def load_data(self, filepath) -> pd.DataFrame:
        return pd.read_csv(filepath)

    def train(self, data: pd.DataFrame, save: bool = True) -> "AdaptiveLearningSystem":
        data = validate_students(data)
        self.reference = {s: np.sort(data[s].to_numpy(dtype=float)) for s in SIGNALS}
        if save:
            joblib.dump(self, config.models_dir() / MODEL_FILE)
        return self

    def load(self) -> "AdaptiveLearningSystem":
        loaded = joblib.load(config.models_dir() / MODEL_FILE)
        if not isinstance(loaded, AdaptiveLearningSystem):
            raise TypeError(
                f"{MODEL_FILE} was created by an older version; retrain with "
                "`python Adaptive-Learning-System.py`.")
        self.reference = loaded.reference
        return self

    def _percentile(self, signal: str, values: np.ndarray) -> np.ndarray:
        ref = self.reference[signal]
        # share of reference students at or below the value (empirical CDF)
        return np.searchsorted(ref, values, side="right") / len(ref)

    def assess(self, student_data: pd.DataFrame) -> list[dict]:
        """Level, action and the reasoning behind it, for each row."""
        if not self.reference:
            self.load()
        data = validate_students(student_data)
        percentiles = {s: self._percentile(s, data[s].to_numpy(dtype=float)) for s in SIGNALS}
        performance = (percentiles["Progress"] + percentiles["AverageScore"]) / 2
        levels = np.digitize(performance, THRESHOLDS)
        return [{
            "level": int(level),
            "action": self.actions[int(level)],
            "performance_percentile": round(float(p), 3),
            "progress_percentile": round(float(pp), 3),
            "score_percentile": round(float(sp), 3),
        } for level, p, pp, sp in zip(levels, performance,
                                       percentiles["Progress"], percentiles["AverageScore"])]

    def predict(self, student_data: pd.DataFrame) -> str:
        """Original API: action text for the first row."""
        return self.assess(student_data.iloc[[0]])[0]["action"]


def run(data_path=None, demo_student_index: int = 0):
    data_path = data_path or config.processed_dir() / config.CLEAN_CSV
    system = AdaptiveLearningSystem()
    data = system.load_data(data_path)
    system.train(data)
    return system, system.assess(data.iloc[[demo_student_index]])[0]
