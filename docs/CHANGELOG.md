# Changelog

## Phase 7 – Local run on Windows

### Fixed
* `pip install -r requirements.txt` failed on Python 3.15 (the laptop's default `python`):
  numpy 2.4.6 has no 3.15 wheel. numpy/scipy are now pinned per Python version
  (2.4.6/1.17.1 on 3.11, 2.5.4/1.18.1 on 3.12+). Verified: clean copy, plain `python -m venv`
  + pip on 3.15 -> 88/88 tests pass and identical model metrics; `npm ci` + build pass.
* `e2e-ai.mjs` could act on a seeded student when its localStorage-based student selection
  lost a race with the app's own first-load selection. It now selects the student through
  the real switcher UI and aborts before any action if the test student is not selected;
  tabs are clicked by `role="tab"` (recommendation cards also contain the word "Collaborative").

### Verified
* Restart persistence on a database copy: all data, recommendations, skills and bandit
  counts identical after a full backend restart; seeding does not re-run on a non-empty DB;
  models retrain at start-up and include new attempts.
* README: Windows run instructions without `Activate.ps1`, Python 3.11-3.15.


## Phase 6 – Full integration verification

### Fixed
* Concurrent first AI requests each started a full model training (4 parallel requests ->
  4 trainings); training is now single-flight (re-entrant lock + double-checked readiness).
* An empty/too-small database crashed AI endpoints with a 500 ("empty vocabulary"); they now
  return 503 `ml_insufficient_data` with an explanation, and start-up logs it calmly.

### Added
* `tests/backend/test_ml_integration.py` (single-flight training, insufficient data, cold
  start, outputs updating as student data changes) and `test_endpoint_coverage.py` (every
  OpenAPI route called with valid data and documented in `docs/API.md`). 88 Python tests.
* `frontend/scripts/lib/browser.mjs` (shared DevTools-protocol driver) and
  `npm run e2e:ai` (36 UI checks incl. responsive overflow at 375/768/1280 px, throttled
  loading skeletons, empty/error states, offline mode).
* Documented model limitations in `docs/ML_MODELS.md`.


## Phase 5 – AI/ML integration

### Added
* `ml/`: recommenders (content-based, item-kNN collaborative, hybrid, popularity),
  Bayesian Knowledge Tracing, LinUCB difficulty bandit, gradient-boosting score
  prediction, behaviour-based learning-style model, point-in-time learner state,
  paired-bootstrap statistics.
* `backend/app/ml_service.py`: trains/evaluates every model from SQLite (background
  thread at start-up), serves per-student outputs from live rows, updates the bandit
  online after each quiz. `backend/app/assistant.py`: grounded assistant with
  optional Claude API (`anthropic` SDK) and automatic fallback.
* 9 endpoints under `/api/ml/*` and `/api/students/{id}/…` (see `docs/API.md`).
* Frontend: rebuilt AI Recommendations page (method switcher, assistant chat,
  skill mastery, adaptive difficulty, predicted scores, learning style), new Model
  Evaluation page with retrain, "Recommended for you" on the dashboard, model-ranked
  next steps on the roadmap. Model outputs carry "ML model output" / "Synthetic
  history" badges; evaluation verdicts are data-driven, never hard-coded.
* Seed generator: per-question answers from a documented learner simulator (+ retakes),
  needed for BKT. 27 new tests (83 Python tests), e2e extended to 21 checks.
* `docs/ML_MODELS.md` with the measured results.

### Results (honest)
On the seeded (synthetic) database no model significantly beats its strongest
baseline; the learning-style model is flagged unreliable. Details in `docs/ML_MODELS.md`.


## Phase 4 – Frontend (React + Vite + Tailwind + Recharts)

### Added
* `frontend/`: React 19 SPA with sidebar navigation (drawer on mobile), student
  switcher, API status indicator, light/dark theme, toasts, lazy-loaded pages.
* Pages: Dashboard, My Learning, Course Catalog, Learning Roadmap, AI
  Recommendations, Progress & Analytics, Profile, Quiz, 404 – all backed by the
  Phase 3 API; loading / error / empty states throughout.
* Working actions: create/edit/delete student, log study time, enrol (with
  prerequisite messages), complete lessons, pause/resume, rate, take graded quizzes.
* Charts (weekly study time, quiz score timeline, scores by topic) with tooltips
  and table view; validated palette per theme.
* `npm run e2e`: headless-browser smoke test (18 checks) using Edge/Chrome via
  the DevTools protocol – no extra packages.
* `docs/FRONTEND.md`, `frontend/.env.example`.

### Fixed during verification
* `useEffect(() => window.scrollTo(...))` returned a Promise in current
  Chromium and crashed React ("destroy is not a function").
* Weekly chart axis rounded 150 min to "3h"; it now plots hours.
* Clipped "100%" axis label; roadmap tracks clipped at the right edge.
* This changelog had been emptied by a failed (cp1252) write during Phase 3 and
  committed empty; restored from version history.

## Phase 3 – Backend (FastAPI + SQLite)

Development order changed at the user's request: application first
(backend → frontend → ML integration), ML improvements afterwards.

### Added
* `backend/app/`: FastAPI app factory, settings from env/`.env`, SQLAlchemy 2.0
  models (10 tables), Pydantic v2 schemas, service layer, 4 routers, 21 endpoints.
* Business rules: prerequisite enforcement, idempotent lesson completion with
  automatic course completion, server-side quiz grading with per-question
  feedback (answer keys never exposed), rating only after completion,
  drop/re-enrol.
* Analytics endpoints: dashboard summary, weekly activity, score trend,
  scores by topic, streaks.
* Consistent JSON error format; validation (422), conflicts (409), 404s,
  no stack traces leaked on 500.
* Seed data: hand-written catalogue (24 courses / 120 lessons / 96 questions)
  + the 100 `sample_data.csv` students + seeded synthetic 12-week history,
  verified to match the original rows. `python -m backend.app.seed --reset`.
* `.env.example`, `docs/API.md`, 30 API tests (56 tests in total).

## Phase 2 – Fix existing functionality, prepare ML architecture

**Baseline protected:** all pre-existing local edits, processed data and model
pickles committed on branch `upgrade/v2` and tagged `baseline-local-2026-11-04`.

### Fixed
* Learning-style classifier: scaling inside a Pipeline fitted on train rows
  only (removes leakage and double scaling); Decision Tree depth tuned by CV;
  results reported next to majority/chance baselines; held-out IDs persisted.
* K-Means: k chosen by silhouette score; cluster profiles saved, not discarded.
* `load_models()` restored; `classify_new_student` works after a restart and
  also returns class probabilities and the student's segment.
* Peer recommender: no longer returns the student as its own match; returns
  exactly *n* results; values in original units; similarity score per peer;
  similarity-weighted content-format suggestion.
* Adaptive model: replaced the leaky RandomForest (which re-learned its own
  label formula at 0.77 CV accuracy) with the explicit percentile rule, fixed
  the single-student bug (always "Advanced"), added the reasoning to the output.
* Preprocessing: `StudentID` stays an integer; fitted imputers/scaler re-usable
  via `transform()`; a clean, unscaled CSV is produced for model training.
* Evaluation: uses the saved held-out set; evaluates all three components with
  baselines; leakage-free check for the peer recommender; writes JSON report.
* Scripts run from any directory; clear error messages instead of tracebacks.

### Added
* `ml/` package (`config`, `schema`, `preprocessing`, `learning_style`,
  `peer_recommender`, `adaptive_level`, `evaluation`, `cli`).
* Input validation (`ml/schema.py`) for ranges, categories, types, IDs.
* `requirements.txt` (pinned, no TensorFlow) and `requirements-dev.txt`.
* `pytest` suite (26 tests) including leakage and backward-compatibility tests.
* `.gitignore`; generated `data/processed`, `models/*`, `reports/` untracked.

### Unchanged
* `sample_data.csv` (a test asserts its SHA-256 matches upstream).
* The five root script names, their commands, their class names and the
  original model file names.
