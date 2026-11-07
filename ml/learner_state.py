"""Point-in-time learner features, built by replaying quiz history in time order.

Every feature for an attempt is computed from information available *before*
that attempt (no look-ahead). Used by the performance predictor (features) and
the difficulty bandit (context, arm, reward).

``attempts`` columns: attempt_id, student_id, quiz_id, course_id, topic, level,
content_format, skills (list), score, attempted_at.
``answers`` maps attempt_id -> list of (skill, correct 0/1).
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

from ml.knowledge_tracing import BKTModel

FEATURES = ["prior_attempts", "prior_mean", "prior_last", "prior_trend", "topic_prior_mean", "level",
            "format_match", "quiz_skill_mastery", "overall_mastery", "is_retake", "prior_answers", "prior_correct"]
CONTEXT_NAMES = ["bias", "prior_mean", "overall_mastery", "experience", "recent_trend"]
TARGET_ZONE = (60.0, 90.0)   # "productive challenge": passed, but not trivially easy


def zone_reward(score: float) -> int:
    return int(TARGET_ZONE[0] <= score < TARGET_ZONE[1])


class LearnerState:
    def __init__(self, bkt: BKTModel, preferred_format: str | None = None):
        self.bkt = bkt
        self.preferred_format = preferred_format
        self.scores: list[float] = []
        self.topic_scores = defaultdict(list)
        self.mastery: dict[str, float] = {}
        self.quiz_counts = defaultdict(int)
        self.n_answers = 0            # question-level evidence: answers given so far ...
        self.n_correct = 0            # ... and how many were right

    def _prior_knowledge(self) -> float:
        """P(known) for a skill not yet tested: the BKT prior given how this learner has answered so far."""
        return self.bkt.initial_knowledge(self.n_correct, self.n_answers)

    def _skill_mastery(self, skill: str) -> float:
        return self.mastery.get(skill, self._prior_knowledge())

    def features(self, quiz: dict) -> dict:
        s = self.scores
        topic = self.topic_scores.get(quiz["topic"], [])
        skills = quiz.get("skills") or []
        return {
            "prior_attempts": len(s),
            "prior_mean": float(np.mean(s)) if s else np.nan,
            "prior_last": s[-1] if s else np.nan,
            "prior_trend": float(np.mean(s[-3:]) - np.mean(s)) if len(s) >= 2 else 0.0,
            "topic_prior_mean": float(np.mean(topic)) if topic else np.nan,
            "level": int(quiz["level"]),
            "format_match": int(bool(self.preferred_format) and quiz.get("content_format") == self.preferred_format),
            "quiz_skill_mastery": float(np.mean([self._skill_mastery(k) for k in skills])) if skills else self._prior_knowledge(),
            "overall_mastery": float(np.mean(list(self.mastery.values()))) if self.mastery else self._prior_knowledge(),
            "is_retake": int(self.quiz_counts[quiz["quiz_id"]] > 0),
            "prior_answers": self.n_answers,
            "prior_correct": self.n_correct,
        }

    def context(self) -> np.ndarray:
        """Bandit context (independent of which quiz is chosen next)."""
        s = self.scores
        return np.array([
            1.0,
            (np.mean(s) if s else 75.0) / 100.0,
            float(np.mean(list(self.mastery.values()))) if self.mastery else self._prior_knowledge(),
            min(len(s), 10) / 10.0,
            (float(np.mean(s[-3:]) - np.mean(s)) / 100.0) if len(s) >= 2 else 0.0,
        ])

    def update(self, quiz: dict, score: float, answers: list[tuple[str, int]]) -> None:
        self.scores.append(float(score))
        self.topic_scores[quiz["topic"]].append(float(score))
        self.quiz_counts[quiz["quiz_id"]] += 1
        for skill, correct in answers:
            self.mastery[skill] = self.bkt.update_knowledge(self._skill_mastery(skill), correct)
            self.n_correct += int(bool(correct))
            self.n_answers += 1


def quiz_meta(row) -> dict:
    return {"quiz_id": int(row["quiz_id"]), "topic": row["topic"], "level": int(row["level"]),
            "content_format": row["content_format"], "skills": list(row["skills"])}


def replay(attempts: pd.DataFrame, answers: dict, preferred: dict, bkt: BKTModel) -> pd.DataFrame:
    """One row per attempt with pre-attempt features, bandit context, arm, reward and target."""
    rows = []
    ordered = attempts.sort_values(["student_id", "attempted_at", "attempt_id"], kind="mergesort")
    for sid, group in ordered.groupby("student_id", sort=False):
        state = LearnerState(bkt, preferred.get(sid))
        for _, a in group.iterrows():
            quiz = quiz_meta(a)
            rows.append({"attempt_id": int(a["attempt_id"]), "student_id": sid, "attempted_at": a["attempted_at"],
                         **state.features(quiz), "context": state.context(), "arm": int(a["level"]),
                         "reward": zone_reward(a["score"]), "score": float(a["score"])})
            state.update(quiz, a["score"], answers.get(int(a["attempt_id"]), []))
    return pd.DataFrame(rows)


def build_state(attempts: pd.DataFrame, answers: dict, preferred_format: str | None, bkt: BKTModel) -> LearnerState:
    """Current state of one student after all their attempts."""
    state = LearnerState(bkt, preferred_format)
    for _, a in attempts.sort_values(["attempted_at", "attempt_id"], kind="mergesort").iterrows():
        state.update(quiz_meta(a), a["score"], answers.get(int(a["attempt_id"]), []))
    return state
