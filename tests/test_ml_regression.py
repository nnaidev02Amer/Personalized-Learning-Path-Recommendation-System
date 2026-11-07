"""Regression tests for two QA bugs (HIGH severity).

BUG-04  BKT marked a skill "mastered" after 0 of 3 correct (and ~97% mastered at 50% accuracy).
        Root causes: a shared prior that ignores how the learner performs elsewhere, plus a fit that
        drifted to a corner of the parameter grid (p_learn = 0.45) where mastery "recovers" after any
        number of wrong answers, because the likelihood surface is nearly flat.
BUG-05  Score prediction contradicted the learner's own record (0% x 3 predicted 82-90% "likely").
        Root causes: almost no training rows from struggling learners (1 of ~750), so the boosted trees
        extrapolated arbitrarily, and the response to the learner's own prior score was not monotonic.

All data here is simulated in memory: nothing touches a real or seeded database.
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import log_loss

from ml import knowledge_tracing, performance
from ml.knowledge_tracing import MASTERY_THRESHOLD, BKTModel
from ml.learner_state import FEATURES, replay

T0 = datetime(2026, 1, 1)
QUIZ_SKILLS = {1: ["s0", "s1", "s0", "s1"], 2: ["s1", "s2", "s1", "s2"], 3: ["s2", "s0", "s2", "s0"]}


def simulate_learners(abilities, attempts_each=5, seed=0):
    """Learners whose every answer is right with probability = their persistent ability (a realistic trait)."""
    rng = np.random.default_rng(seed)
    obs_rows, attempt_rows, answers = [], [], {}
    attempt_id = 0
    for sid, theta in enumerate(abilities, start=1):
        for a in range(attempts_each):
            attempt_id += 1
            quiz = a % 3 + 1
            when = T0 + timedelta(days=a, minutes=sid)
            pairs = []
            for skill in QUIZ_SKILLS[quiz]:
                c = int(rng.random() < theta)
                pairs.append((skill, c))
                obs_rows.append((sid, skill, when, c))
            answers[attempt_id] = pairs
            attempt_rows.append((attempt_id, sid, quiz, quiz, "T", 1, "Videos", QUIZ_SKILLS[quiz],
                                 100.0 * sum(c for _, c in pairs) / len(pairs), when))
    obs = pd.DataFrame(obs_rows, columns=["student_id", "skill", "attempted_at", "correct"])
    attempts = pd.DataFrame(attempt_rows, columns=["attempt_id", "student_id", "quiz_id", "course_id", "topic", "level",
                                                   "content_format", "skills", "score", "attempted_at"])
    return obs, attempts, answers


def population(n=160, seed=0):
    """Accuracy varies a lot between learners (Beta(6,2): mean .75, sd ~.14), as in real course data."""
    return np.random.default_rng(seed).beta(6, 2, size=n)


def answers_frame(pairs):
    return pd.DataFrame([(1, skill, T0 + timedelta(minutes=i), c) for i, (skill, c) in enumerate(pairs)],
                        columns=["student_id", "skill", "attempted_at", "correct"])


@pytest.fixture(scope="module")
def fitted_bkt():
    obs, _, _ = simulate_learners(population())
    return BKTModel().fit(obs)


# =================================================================== BKT (BUG-04)
def test_repeated_wrong_answers_never_read_as_mastered(fitted_bkt):
    """0 of 3 (or more) correct on a skill must not be reported as mastered."""
    for n_wrong in (3, 4, 6):
        m = fitted_bkt.mastery(answers_frame([("x", 0)] * n_wrong))["x"]
        assert m["mastery"] < MASTERY_THRESHOLD, f"{n_wrong} wrong answers -> mastery {m['mastery']}"
        assert m["accuracy"] == 0


def test_zero_of_twelve_across_three_skills_flags_every_skill_as_a_gap(fitted_bkt):
    """The QA scenario: three failed attempts at a quiz covering three skills."""
    wrong = [(f"s{i % 3}", 0) for i in range(12)]
    result = fitted_bkt.mastery(answers_frame(wrong))
    assert set(result) == {"s0", "s1", "s2"}
    assert all(v["mastery"] < MASTERY_THRESHOLD for v in result.values())


def test_mastery_falls_with_every_additional_wrong_answer(fitted_bkt):
    levels = [fitted_bkt.mastery(answers_frame([("x", 0)] * k))["x"]["mastery"] for k in range(1, 7)]
    assert all(b < a for a, b in zip(levels, levels[1:])), levels


def test_mastery_still_recovers_when_the_learner_starts_answering_correctly(fitted_bkt):
    """The fix must not make mastery sticky: learning is still possible."""
    failing = fitted_bkt.mastery(answers_frame([("x", 0)] * 3))["x"]["mastery"]
    recovered = fitted_bkt.mastery(answers_frame([("x", 0)] * 3 + [("x", 1)] * 4))["x"]["mastery"]
    assert recovered > failing + 0.3
    assert fitted_bkt.mastery(answers_frame([("x", 1)] * 4))["x"]["mastery"] > MASTERY_THRESHOLD


def test_prior_comes_from_how_the_learner_performs_elsewhere(fitted_bkt):
    assert np.isfinite(fitted_bkt.prior_strength), "heterogeneous learners must select an individualised prior"
    strong = fitted_bkt.initial_knowledge(n_correct=12, n_total=12)
    weak = fitted_bkt.initial_knowledge(n_correct=0, n_total=12)
    assert weak < MASTERY_THRESHOLD < strong
    assert fitted_bkt.initial_knowledge() == pytest.approx(fitted_bkt.p_init)      # no evidence -> population prior


def test_other_skills_inform_a_skill_with_a_single_answer(fitted_bkt):
    """One wrong answer on a new skill after a perfect record elsewhere vs after a failing record."""
    strong_elsewhere = answers_frame([("a", 1)] * 8 + [("x", 0)])
    weak_elsewhere = answers_frame([("a", 0)] * 8 + [("x", 0)])
    assert (fitted_bkt.mastery(strong_elsewhere)["x"]["mastery"]
            > fitted_bkt.mastery(weak_elsewhere)["x"]["mastery"])


def test_individualised_prior_predicts_held_out_answers_better_than_classic_bkt():
    # Large enough that the benefit is statistically detectable; with little data the conservative
    # fit rule (correctly) falls back to classic BKT, which would make the comparison vacuous.
    obs, _, _ = simulate_learners(population(600, seed=3), seed=3)
    train_ids = set(range(1, 421))
    train, test = obs[obs.student_id.isin(train_ids)], obs[~obs.student_id.isin(train_ids)]
    model = BKTModel().fit(train)
    assert np.isfinite(model.prior_strength)
    classic = BKTModel(model.p_init, model.p_learn, model.p_slip, model.p_guess)           # same params, no individual prior
    p_new, y = model.predict_sequences(test)
    p_old, _ = classic.predict_sequences(test)
    assert log_loss(y, np.clip(p_new, 1e-6, 1 - 1e-6)) < log_loss(y, np.clip(p_old, 1e-6, 1 - 1e-6))


def test_fit_is_conservative_and_reports_how_many_fits_are_equivalent():
    obs, _, _ = simulate_learners(population(), seed=1)
    model = BKTModel().fit(obs)
    assert model.n_equivalent_fits >= 1
    assert model.p_guess <= 0.3 and model.p_slip <= 0.25                                 # degeneracy bounds
    assert model.params["prior_strength"] is None or model.params["prior_strength"] > 0   # JSON-serialisable


def test_classic_bkt_is_still_available_as_a_special_case():
    model = BKTModel(p_init=0.4, p_learn=0.1, p_slip=0.1, p_guess=0.2)                     # prior_strength defaults to inf
    assert model.initial_knowledge(0, 10) == pytest.approx(model.initial_knowledge(10, 10))
    assert model.params["prior_strength"] is None


def test_bkt_evaluation_uses_only_earlier_answers_and_reports_baselines():
    obs, _, _ = simulate_learners(population(120, seed=5), seed=5)
    report = knowledge_tracing.evaluate(obs)
    assert set(report["results"]) >= {"bkt", "baseline_global_accuracy", "baseline_skill_accuracy",
                                      "baseline_student_running_accuracy"}
    assert report["results"]["bkt"]["log_loss"] <= report["results"]["baseline_global_accuracy"]["log_loss"]


# ====================================================== score prediction (BUG-05)
@pytest.fixture(scope="module")
def trained_predictor():
    obs, attempts, answers = simulate_learners(population(200, seed=7), seed=7)
    bkt = BKTModel().fit(obs)
    rows = replay(attempts, answers, {}, bkt)
    return performance.make_model().fit(rows[FEATURES], rows["score"]), rows


def feature_row(answers_correct, answers_total, *, retake=0, mastery=None, level=1):
    pct = 100.0 * answers_correct / answers_total if answers_total else np.nan
    m = mastery if mastery is not None else (0.3 + 0.6 * answers_correct / answers_total if answers_total else 0.8)
    return pd.DataFrame([dict(prior_attempts=answers_total // 4, prior_mean=pct, prior_last=pct, prior_trend=0.0,
                              topic_prior_mean=pct, level=level, format_match=0, quiz_skill_mastery=m,
                              overall_mastery=m, is_retake=retake, prior_answers=answers_total,
                              prior_correct=answers_correct)])[FEATURES]


def predict(model, *args, **kw):
    return float(model.predict(feature_row(*args, **kw))[0])


def test_learner_who_failed_three_attempts_is_predicted_clearly_below_a_strong_learner(trained_predictor):
    model, rows = trained_predictor
    weak = predict(model, 0, 12, retake=1, mastery=0.4)          # 0% on the quiz, three times
    strong = predict(model, 12, 12, retake=1, mastery=0.95)
    typical = float(rows["score"].mean())
    assert weak < 60, f"0 of 12 correct was predicted {weak:.1f}"
    assert weak < typical - 15
    assert strong - weak > 30


def test_prediction_never_decreases_as_the_learners_record_improves(trained_predictor):
    model, _ = trained_predictor
    sweep = [predict(model, c, 12, mastery=0.3 + 0.6 * c / 12) for c in range(13)]
    assert all(b >= a - 1e-9 for a, b in zip(sweep, sweep[1:])), sweep
    assert sweep[-1] - sweep[0] > 30


def test_prediction_is_monotone_in_each_constrained_signal(trained_predictor):
    model, _ = trained_predictor
    mastery = [predict(model, 6, 12, mastery=m) for m in np.linspace(0, 1, 11)]
    retake = [predict(model, 6, 12, retake=r) for r in (0, 1)]
    assert all(b >= a - 1e-9 for a, b in zip(mastery, mastery[1:])), mastery
    assert retake[1] >= retake[0] - 1e-9


def test_prediction_follows_the_record_more_with_more_evidence(trained_predictor):
    """With few answers the estimate stays near the population mean; with many it follows the learner."""
    model, rows = trained_predictor
    mean = float(rows["score"].mean())
    few = predict(model, 0, 2)
    many = predict(model, 0, 20)
    assert many < few < mean + 1


def test_cold_start_prediction_is_the_population_expectation(trained_predictor):
    model, rows = trained_predictor
    cold = float(model.predict(feature_row(0, 0))[0])
    assert abs(cold - float(rows["score"].mean())) < 8


def test_predictions_stay_in_range(trained_predictor):
    model, _ = trained_predictor
    for c, n in ((0, 40), (40, 40), (0, 0)):
        assert 0 <= predict(model, c, n) <= 100


def test_shrinkage_strength_is_learned_from_the_data_not_hard_coded():
    homogeneous = simulate_learners([0.7] * 150, seed=11)           # nobody differs -> history is uninformative
    varied = simulate_learners(np.r_[np.full(75, 0.1), np.full(75, 0.95)], seed=11)   # strongly persistent traits

    def kappa(sim):
        obs, attempts, answers = sim
        rows = replay(attempts, answers, {}, BKTModel().fit(obs))
        return performance.make_model().fit(rows[FEATURES], rows["score"]).kappa_

    assert kappa(homogeneous) > 4 * kappa(varied)
    assert kappa(varied) <= 4


def test_performance_evaluation_reports_the_ability_anchor_and_beats_the_naive_baselines():
    obs, attempts, answers = simulate_learners(population(220, seed=13), attempts_each=6, seed=13)
    report = performance.evaluate(attempts, answers, obs, {})
    res = report["results"]
    assert {"gradient_boosting", "baseline_train_mean", "baseline_student_prior_mean", "ability_only"} <= set(res)
    assert res["gradient_boosting"]["mae"] < min(res["baseline_train_mean"]["mae"], res["baseline_student_prior_mean"]["mae"])
    assert report["beats_baseline"] == (report["vs_best_baseline_abs_error"]["ci95"][0] > 0)
    assert report["ability_prior_strength"] in performance.KAPPAS
    assert "feature_importance" in report                       # the UI reads this key
