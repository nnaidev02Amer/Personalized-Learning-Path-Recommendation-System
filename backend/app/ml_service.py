"""Bridge between the SQLite database and the ``ml`` package.

* ``MLService.train(db)`` reads the whole database into DataFrames, evaluates
  every model against its baselines, then fits production models on all data.
* Per-student endpoints combine those fitted models with the student's *live*
  rows (so a lesson or quiz completed a second ago is reflected immediately).
* The difficulty bandit is also updated online after each quiz submission.

Training data provenance is reported with every result: seeded students carry
synthetic histories (``students.is_synthetic``); anything created through the
API is real usage of this installation.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.app.errors import NotFound
from backend.app.models import Course, Student
from ml import bandit as bandit_mod
from ml import config as ml_config
from ml import knowledge_tracing, performance, recsys, style_model
from ml.knowledge_tracing import MASTERY_THRESHOLD, BKTModel
from ml.learner_state import CONTEXT_NAMES, FEATURES, build_state, quiz_meta, replay, zone_reward

log = logging.getLogger("backend.ml")
REPORT_FILE = "ml_evaluation.json"


# ------------------------------------------------------------- data loading
def load_frames(db: Session) -> dict[str, pd.DataFrame]:
    conn = db.connection()
    q = lambda sql: pd.read_sql_query(sql, conn)  # noqa: E731
    courses = q("SELECT id, code, title, description, topic, level, content_format, skills FROM courses")
    courses["skills"] = courses["skills"].apply(lambda s: json.loads(s) if isinstance(s, str) else (s or []))
    prereq = q("SELECT course_id, prerequisite_id FROM course_prerequisites")
    pmap = prereq.groupby("course_id")["prerequisite_id"].apply(list).to_dict()
    courses["prerequisite_ids"] = courses["id"].map(lambda c: [int(x) for x in pmap.get(c, [])])

    students = q("SELECT id, age, learning_style, preferred_content, daily_goal_minutes, is_synthetic FROM students")
    enrollments = q("SELECT id, student_id, course_id, status, rating, enrolled_at FROM enrollments")
    enrollments["enrolled_at"] = pd.to_datetime(enrollments["enrolled_at"])
    attempts = q("""SELECT a.id AS attempt_id, a.student_id, a.quiz_id, a.score, a.answers, a.attempted_at,
                           c.id AS course_id, c.topic, c.level, c.content_format, c.skills
                    FROM quiz_attempts a JOIN quizzes z ON z.id = a.quiz_id JOIN courses c ON c.id = z.course_id""")
    attempts["attempted_at"] = pd.to_datetime(attempts["attempted_at"])
    attempts["skills"] = attempts["skills"].apply(lambda s: json.loads(s) if isinstance(s, str) else (s or []))
    attempts["answers"] = attempts["answers"].apply(lambda s: json.loads(s) if isinstance(s, str) else s)
    questions = q("SELECT quiz_id, position, skill, correct_option FROM quiz_questions ORDER BY quiz_id, position")
    activity = q("SELECT student_id, course_id, minutes FROM activity_logs")
    return {"courses": courses, "students": students, "enrollments": enrollments, "attempts": attempts,
            "questions": questions, "activity": activity}


def answer_observations(attempts: pd.DataFrame, questions: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Per-question correctness rows (for BKT) and attempt_id -> [(skill, correct)]."""
    by_quiz = {qid: list(zip(g["skill"], g["correct_option"])) for qid, g in questions.groupby("quiz_id")}
    rows, per_attempt = [], {}
    for a in attempts.itertuples(index=False):
        if not isinstance(a.answers, list):
            continue          # attempts without per-question answers carry no skill evidence
        pairs = []
        for (skill, key), ans in zip(by_quiz.get(a.quiz_id, []), a.answers):
            c = int(ans == key)
            pairs.append((skill, c))
            rows.append({"student_id": a.student_id, "skill": skill, "attempted_at": a.attempted_at, "correct": c})
        per_attempt[int(a.attempt_id)] = pairs
    return pd.DataFrame(rows, columns=["student_id", "skill", "attempted_at", "correct"]), per_attempt


# ------------------------------------------------------------------ service
class MLService:
    def __init__(self):
        self._lock = threading.Lock()
        self.trained_at: str | None = None
        self.report: dict | None = None

    @property
    def ready(self) -> bool:
        return self.trained_at is not None

    def ensure_trained(self, db: Session) -> None:
        if not self.ready:
            self.train(db)

    def train(self, db: Session) -> dict:
        with self._lock:
            started = time.perf_counter()
            f = load_frames(db)
            obs, per_attempt = answer_observations(f["attempts"], f["questions"])
            preferred = f["students"].set_index("id")["preferred_content"].to_dict()
            style_features = style_model.build_features(f["students"], f["enrollments"], f["attempts"],
                                                        f["activity"], f["courses"])

            # 1) Evaluation against baselines (held-out data only).
            report = {
                "recommendations": recsys.evaluate(f["courses"], f["enrollments"], f["students"]),
                "knowledge_tracing": knowledge_tracing.evaluate(obs),
                "performance_prediction": performance.evaluate(f["attempts"], per_attempt, obs, preferred),
                "learning_style": style_model.evaluate(style_features),
            }

            # 2) Production models on all data.
            self.bkt = BKTModel().fit(obs)
            rows = replay(f["attempts"], per_attempt, preferred, self.bkt)
            report["adaptive_difficulty"] = bandit_mod.evaluate(rows)
            self.recommender = recsys.CourseRecommender(**report["recommendations"]["tuned_params"]).fit(
                f["courses"], f["enrollments"])
            self.performance = performance.make_model().fit(rows[FEATURES], rows["score"])
            self.performance_mae = report["performance_prediction"]["results"]["gradient_boosting"]["mae"]
            self.bandit = bandit_mod.LinUCB(len(CONTEXT_NAMES)).fit(rows["context"], rows["arm"], rows["reward"])
            self.style = style_model.fit(style_features)
            self.style_eval = report["learning_style"]
            self.courses = f["courses"]

            synthetic = int(f["students"]["is_synthetic"].sum())
            report["training_data"] = {
                "students": int(len(f["students"])), "synthetic_students": synthetic,
                "real_students": int(len(f["students"]) - synthetic),
                "enrollments": int(len(f["enrollments"])), "quiz_attempts": int(len(f["attempts"])),
                "answer_observations": int(len(obs)),
                "note": "Seeded students have SYNTHETIC histories generated by a learner simulator; metrics "
                        "describe how well the models recover that simulated behaviour, not real-world efficacy.",
            }
            self.trained_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            report["trained_at"] = self.trained_at
            report["training_seconds"] = round(time.perf_counter() - started, 2)
            self.report = report
            try:
                (ml_config.reports_dir() / REPORT_FILE).write_text(json.dumps(report, indent=2, default=str),
                                                                    encoding="utf-8")
            except OSError as exc:               # reporting must never break training
                log.warning("Could not write ML report: %s", exc)
            log.info("ML models trained in %.1fs", report["training_seconds"])
            return report

    # ----------------------------------------------------------- per student
    def _student(self, db: Session, student_id: int) -> Student:
        student = db.get(Student, student_id)
        if student is None:
            raise NotFound(f"Student {student_id} not found")
        self.ensure_trained(db)
        return student

    def _student_frames(self, db: Session, student_id: int):
        conn = db.connection()
        hist = pd.read_sql_query(text("SELECT course_id, status, rating, enrolled_at FROM enrollments "
                                      "WHERE student_id = :sid"), conn, params={"sid": student_id})
        f = {"attempts": pd.read_sql_query(text(
            """SELECT a.id AS attempt_id, a.student_id, a.quiz_id, a.score, a.answers, a.attempted_at,
                      c.id AS course_id, c.topic, c.level, c.content_format, c.skills
               FROM quiz_attempts a JOIN quizzes z ON z.id = a.quiz_id JOIN courses c ON c.id = z.course_id
               WHERE a.student_id = :sid"""), conn, params={"sid": student_id}),
             "questions": pd.read_sql_query("SELECT quiz_id, position, skill, correct_option FROM quiz_questions "
                                            "ORDER BY quiz_id, position", conn)}
        att = f["attempts"]
        att["attempted_at"] = pd.to_datetime(att["attempted_at"])
        att["skills"] = att["skills"].apply(lambda s: json.loads(s) if isinstance(s, str) else (s or []))
        att["answers"] = att["answers"].apply(lambda s: json.loads(s) if isinstance(s, str) else s)
        obs, per_attempt = answer_observations(att, f["questions"])
        return hist, att, obs, per_attempt

    def provenance(self, student: Student) -> dict:
        return {"model_output": True, "trained_at": self.trained_at,
                "student_history": "synthetic (seeded)" if student.is_synthetic else "real (created in this app)"}

    def recommendations(self, db: Session, student_id: int, method: str = "hybrid", limit: int = 5) -> dict:
        student = self._student(db, student_id)
        hist, *_ = self._student_frames(db, student_id)
        items = self.recommender.recommend(hist, student.preferred_content, method=method, n=limit)
        rec_report = self.report["recommendations"]
        ev = rec_report["methods"][method]
        cmp = rec_report["protocols"]["unlocked_courses"]["vs_popularity_ndcg"].get(method)
        return {"student_id": student_id, "method": method, "items": items,
                "evaluation": {"ndcg_at_5": ev["ndcg_at_k"], "hit_rate_at_5": ev["hit_rate_at_k"],
                               "popularity_ndcg_at_5": rec_report["methods"]["popularity"]["ndcg_at_k"],
                               "beats_popularity": cmp["significant"] if cmp else None},
                **self.provenance(student)}

    def skills(self, db: Session, student_id: int) -> dict:
        student = self._student(db, student_id)
        hist, _att, obs, _ = self._student_frames(db, student_id)
        mastery = self.bkt.mastery(obs)
        skill_topic = {s: (c["topic"], c["title"]) for _, c in self.courses.iterrows() for s in c["skills"]}
        skills = [{"skill": s, "topic": skill_topic.get(s, ("Other", ""))[0], **m,
                   "mastered": m["mastery"] >= MASTERY_THRESHOLD} for s, m in mastery.items()]
        skills.sort(key=lambda x: x["mastery"])
        # Gaps that matter now: assessed-but-weak skills, plus untested skills of active courses.
        active_ids = set(hist.loc[hist["status"] == "active", "course_id"].astype(int))
        upcoming = sorted({s for _, c in self.courses.iterrows() if int(c["id"]) in active_ids for s in c["skills"]}
                          - set(mastery))
        topics = {}
        for s in skills:
            topics.setdefault(s["topic"], []).append(s["mastery"])
        return {"student_id": student_id, "params": self.bkt.params, "threshold": MASTERY_THRESHOLD,
                "skills": skills,
                "gaps": [s for s in skills if not s["mastered"]][:8],
                "not_yet_assessed": upcoming,
                "topics": sorted(({"topic": t, "mean_mastery": round(float(np.mean(v)), 4), "skills": len(v)}
                                  for t, v in topics.items()), key=lambda x: x["mean_mastery"]),
                "evaluation": self.report["knowledge_tracing"]["results"],
                "beats_baseline": self.report["knowledge_tracing"]["beats_best_baseline"],
                **self.provenance(student)}

    def _state(self, student, att, per_attempt):
        return build_state(att, per_attempt, student.preferred_content, self.bkt)

    def adaptive_difficulty(self, db: Session, student_id: int) -> dict:
        student = self._student(db, student_id)
        _hist, att, _obs, per_attempt = self._student_frames(db, student_id)
        state = self._state(student, att, per_attempt)
        x = state.context()
        est = self.bandit.arm_estimates(x)
        greedy = self.bandit.choose(x, explore=False)
        chosen = self.bandit.choose(x, explore=True)
        return {"student_id": student_id,
                "recommended_level": chosen, "recommended_difficulty": bandit_mod.ARM_NAMES[chosen],
                "exploring": chosen != greedy,
                "arms": [{"level": a, "difficulty": bandit_mod.ARM_NAMES[a],
                          "expected_success": round(v["expected_reward"], 4),
                          "uncertainty": round(v["uncertainty"], 4), "observations": v["observations"]}
                         for a, v in est.items()],
                "context": dict(zip(CONTEXT_NAMES, np.round(x, 4).tolist())),
                "reward_definition": "quiz score in [60, 90): passed but challenging",
                "evaluation": self.report["adaptive_difficulty"]["reward_model"],
                "beats_baseline": self.report["adaptive_difficulty"]["beats_baseline"],
                **self.provenance(student)}

    def observe_attempt(self, db: Session, student_id: int, attempt_id: int) -> None:
        """Online bandit update after a quiz submission (context = state before it)."""
        if not self.ready:
            return
        student = db.get(Student, student_id)
        _hist, att, _obs, per_attempt = self._student_frames(db, student_id)
        current = att[att["attempt_id"] == attempt_id]
        if current.empty:
            return
        before = att[att["attempted_at"] < current["attempted_at"].iloc[0]]
        x = self._state(student, before, per_attempt).context()
        row = current.iloc[0]
        with self._lock:
            self.bandit.update(x, int(row["level"]), zone_reward(float(row["score"])))

    def predictions(self, db: Session, student_id: int) -> dict:
        student = self._student(db, student_id)
        hist, att, _obs, per_attempt = self._student_frames(db, student_id)
        state = self._state(student, att, per_attempt)
        active = hist[hist["status"].isin(["active", "completed"])]["course_id"].astype(int).tolist()
        quizzes = {int(c.id): c for c in db.scalars(select(Course).where(Course.id.in_(active)))}
        items = []
        for cid in active:
            course = quizzes[cid]
            for quiz in course.quizzes:
                meta = {"quiz_id": quiz.id, "topic": course.topic, "level": course.level,
                        "content_format": course.content_format, "skills": course.skills}
                feats = pd.DataFrame([state.features(meta)])[FEATURES]
                pred = float(np.clip(self.performance.predict(feats)[0], 0, 100))
                taken = int(state.quiz_counts.get(quiz.id, 0))
                items.append({"quiz_id": quiz.id, "quiz_title": quiz.title, "course_id": cid,
                              "course_title": course.title, "status": hist.loc[hist["course_id"] == cid, "status"].iloc[0],
                              "predicted_score": round(pred, 1), "expected_error_mae": self.performance_mae,
                              "pass_probability_hint": "likely" if pred - self.performance_mae >= quiz.pass_score
                              else "uncertain" if pred + self.performance_mae >= quiz.pass_score else "at risk",
                              "previous_attempts": taken})
        items.sort(key=lambda i: (i["status"] != "active", i["predicted_score"]))
        return {"student_id": student_id, "items": items,
                "evaluation": self.report["performance_prediction"]["results"],
                "beats_baseline": self.report["performance_prediction"]["beats_baseline"],
                **self.provenance(student)}

    def learning_style(self, db: Session, student_id: int) -> dict:
        student = self._student(db, student_id)
        f = load_frames(db)
        feats = style_model.build_features(f["students"][f["students"]["id"] == student_id], f["enrollments"],
                                           f["attempts"], f["activity"], f["courses"])
        pred = style_model.predict(self.style, feats)
        return {"student_id": student_id, **pred, "self_reported_style": student.learning_style,
                "reliable": self.style_eval["reliable"],
                "evaluation": {k: self.style_eval[k] for k in
                               ("cv_accuracy_mean", "cv_accuracy_std", "baseline_majority_accuracy", "chance_accuracy")},
                "advice": None if self.style_eval["reliable"] else
                "The model does not beat the majority-class baseline on this data, so the prediction should not "
                "be relied on; the self-reported style is used for personalisation.",
                **self.provenance(student)}
