# Personalized Learning Path Recommendation System

A full-stack **local demonstration** of a personalised learning platform: a React web app (branded *PathWise* in the UI) backed by a FastAPI + SQLite API and a set of machine-learning models that recommend courses, track skill mastery, predict quiz scores and suggest a difficulty level for each learner.

> **Read this first.** This is a learning/portfolio project meant to run on your own machine. It has **role-based sign-in (administrator / student)** that has not had an independent security review (see [Security considerations](#24-security-considerations)), ships with a **synthetic** sample dataset, and its models are evaluated honestly against baselines: most of them do **not** reliably beat simple baselines on this data (see [Machine learning model information](#21-machine-learning-model-information)). It is not production software.

---

## Table of contents

1. [Project title](#personalized-learning-path-recommendation-system)
2. [Project overview](#2-project-overview)
3. [Problem statement](#3-problem-statement)
4. [Project objectives](#4-project-objectives)
5. [Key features](#5-key-features)
6. [AI/ML functionality](#6-aiml-functionality)
7. [How the system works](#7-how-the-system-works)
8. [Technology stack](#8-technology-stack)
9. [Project architecture](#9-project-architecture)
10. [Complete folder structure](#10-complete-folder-structure)
11. [System requirements and prerequisites](#11-system-requirements-and-prerequisites)
12. [Installation and setup](#12-installation-and-setup)
13. [Environment variable configuration](#13-environment-variable-configuration)
14. [Database setup and initialization](#14-database-setup-and-initialization)
15. [How to run the backend](#15-how-to-run-the-backend)
16. [How to run the frontend](#16-how-to-run-the-frontend)
17. [How to access and use the application](#17-how-to-access-and-use-the-application)
18. [API documentation and important endpoints](#18-api-documentation-and-important-endpoints)
19. [How to run automated tests](#19-how-to-run-automated-tests)
20. [How to build the frontend for production](#20-how-to-build-the-frontend-for-production)
21. [Machine learning model information](#21-machine-learning-model-information)
22. [Sample workflow](#22-sample-workflow)
23. [Known issues and limitations](#23-known-issues-and-limitations)
24. [Security considerations](#24-security-considerations)
25. [Future improvements](#25-future-improvements)
26. [Contributing guidelines](#26-contributing-guidelines)
27. [License and original project attribution](#27-license-and-original-project-attribution)
28. [Author / project credits](#28-author--project-credits)

---

## 2. Project overview

The application lets a learner browse a course catalogue, enrol (subject to prerequisites), complete lessons, take quizzes with instant scoring and explanations, and follow a roadmap of what to study next. Behind the scenes the backend trains several models from the data in its own SQLite database and serves their outputs per student:

- hybrid **course recommendations** (collaborative + content-based filtering),
- **skill mastery / gap** estimates (Bayesian Knowledge Tracing),
- **quiz-score prediction**,
- an **adaptive difficulty** suggestion (contextual bandit),
- a **learning-style** prediction (flagged unreliable on this data),
- a **grounded learning assistant** (built-in rules; optionally Claude).

The repository started as a small set of five Python scripts and one CSV file (see [Original project attribution](#27-license-and-original-project-attribution)) and was extended into a working web application. Every model comes with an evaluation against baselines, visible on the **Model Evaluation** page.

**Quick start (Windows PowerShell, from the repository root)** – full details in [sections 12–17](#12-installation-and-setup):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload   # terminal 1 -> http://127.0.0.1:8000/docs
cd frontend; npm install; npm run dev                                  # terminal 2 -> http://localhost:5173
```

## 3. Problem statement

Learners following an online curriculum face a sequence of choices: which course next, how hard it should be, which skills are weak, and whether they are on track. A fixed syllabus ignores individual progress and performance. This project explores how a small learning platform can use the data it already collects (enrolments, lesson completions, quiz answers, study time) to personalise those decisions, and how to report honestly how much those models actually help.

## 4. Project objectives

- Provide a complete, runnable learning workflow (catalogue → enrolment → lessons → quizzes → analytics) on a real API and database.
- Recommend only courses a learner can actually take (prerequisites satisfied, not already taken) and explain every recommendation.
- Estimate skill mastery and predict quiz outcomes from a learner's own history, without look-ahead leakage.
- Adapt the suggested difficulty as new quiz results arrive.
- Evaluate every model against baselines with confidence intervals, and say so plainly when it does not win.
- Keep the project reproducible: pinned dependencies, seeded data, automated tests.

## 5. Key features

**Learning workflow**
- Dashboard with courses completed, average quiz score, 7-day study time against the daily goal, streak, weekly activity chart and recent quiz results.
- Course Catalog with search plus topic, level, format and status filters; course detail dialog with lessons, skills and prerequisites. Courses are *Available*, *In progress*, *Completed*, *Paused* or *Locked*.
- Enrolment with server-enforced prerequisites; lesson completion with automatic course completion after the last lesson; pause and resume; star rating for completed courses.
- Quizzes with server-side grading, per-question explanations, retakes and a pass mark. The quiz API never exposes the answer key.
- Learning Roadmap: every topic track ordered by level with locks and a "next steps" list ranked by the recommender.
- Progress & Analytics: completion, weekly study time, quiz history, score trend and topic scores over a selectable range.
- Profile: edit name/email/age/goal/learning style/preferred format with validation; log self-study time. Administrators can also create and delete students.
- Light/dark theme, responsive layout, "API connected / offline" indicator, loading, empty and error states.

**Accounts and roles** (details: [docs/AUTHENTICATION.md](docs/AUTHENTICATION.md))
- Sign-in with **HttpOnly cookie sessions**, Argon2id password hashing, CSRF protection, login rate limiting and account lockout. No default accounts: the first administrator is created from the command line.
- **Administrators**: dashboard and monitoring table (enrolments, quiz averages, at-risk learners), create student accounts or attach a login to an existing seeded student, reset passwords, disable accounts, manage courses (create, archive, delete unused), Model Evaluation and retraining.
- **Students** (created by an administrator, or by self-registration when `ALLOW_SELF_REGISTRATION=true`): enrol in several courses and see **only their own** enrolments, progress, quiz history, recommendations and model outputs, including per-course *Insights*.

**AI/ML**
- AI Recommendations page with four methods (hybrid, collaborative, content-based, popularity baseline) and reasons for every item.
- Skill mastery, adaptive difficulty, predicted quiz scores and learning-style cards, each labelled as model output and showing how it compared with a baseline.
- AI learning assistant (answers from the learner's data and model outputs).
- Course *Insights* page and `?course_id=` filters: skills, difficulty, predicted quiz score and next steps limited to one enrolled course (the models themselves are still trained jointly on all learners; there are no per-course models).
- Recommendation history (a new entry is saved only when the suggested list changes).
- Model Evaluation page (**administrators only**): all models vs. baselines with 95% bootstrap confidence intervals, an evaluation-protocol switch, and a **Retrain on current data** button.

## 6. AI/ML functionality

All model code lives in the importable `ml/` package (no web code). `backend/app/ml_service.py` loads the database into DataFrames, trains and evaluates the models, and serves per-student outputs.

### Knowledge tracing – `ml/knowledge_tracing.py`
Bayesian Knowledge Tracing (Corbett & Anderson, 1994): each skill is a hidden known/not-known state updated after every answer using slip, guess and learn probabilities. Two details matter here:

- **Individualised prior.** A skill the learner has not been tested on starts from their accuracy on *other* skills, shrunk toward the population. The shrinkage strength is fitted; classic BKT is the special case where it is infinite.
- **Conservative fitting.** Parameters are shared across skills and fitted by maximum likelihood over a bounded grid (guess ≤ 0.3, slip ≤ 0.25, learn ≤ 0.3). Because the likelihood surface is nearly flat, the most conservative of the statistically indistinguishable fits is chosen.

A skill counts as *mastered* at mastery ≥ 0.6; assessed skills below that are *gaps*, alongside untested skills of the learner's active courses.

### Learner state management – `ml/learner_state.py`
Replays a learner's quiz history in time order and builds **point-in-time** features, using only information available before each attempt: number of prior attempts, prior mean/last/trend of scores, topic history, course level, preferred-format match, BKT mastery (of the quiz's skills and overall), retake flag, and answer-level counts (`prior_answers`, `prior_correct`). The same state also produces the context vector for the difficulty bandit. `replay()` builds training rows for every attempt; `build_state()` gives the current state of one student.

### Performance analysis – `ml/performance.py` and `/progress`
- **Quiz-score prediction** is an *ability-anchored gradient boosting* model: an empirical-Bayes (Beta-Binomial) estimate of the learner's ability from every earlier answer (shrinkage strength estimated from the data), plus a small, regularised gradient-boosted residual with monotonic constraints, so a better record can never lower the prediction. Evaluation is chronological: models are fitted on earlier attempts and the last 20% are predicted.
- **Progress analytics** (`GET /api/students/{id}/progress`) computes overall completion, per-course progress, weekly activity, the quiz-score timeline, a half-vs-half and a slope-per-week score trend, and scores by topic.

### Recommendation process – `ml/recsys.py`
1. Candidates are the courses the learner can take now: prerequisites completed and not already taken.
2. **Collaborative**: item-kNN over implicit feedback (completed ≈ 1, adjusted by rating; active 0.8; dropped 0.2), with shrinkage.
3. **Content-based**: TF-IDF of course text, topic affinity and preferred-format match; this also carries cold-start learners.
4. **Hybrid**: a min-max blend of the two with a weight tuned on held-out students (the evaluation selects it automatically).
5. **Popularity** is kept as the baseline. Every result carries human-readable reasons and component scores.

### Adaptive difficulty – `ml/bandit.py`
A LinUCB contextual bandit with three arms (Beginner, Intermediate, Advanced). The reward is a quiz score in [60, 90) ("passed, but challenging"). It is warm-started offline from historical attempts and updated online after every quiz submitted through the API. When an arm has little data the card says the suggestion is exploratory.

### Learning style – `ml/style_model.py`
A decision tree on profile and behaviour features, evaluated with 5-fold nested cross-validation against a majority-class baseline. On this dataset it does **not** beat the baseline, so the API returns the prediction with `reliable: false` and the UI keeps using the self-reported style.

### Assistant – `backend/app/assistant.py`
Two providers: a built-in **rules** provider that detects the question's intent and answers from the model outputs using fixed templates (default, no key needed), and an optional **Claude** provider (official `anthropic` SDK) that receives the same grounding context. Any API error falls back to the built-in answer.

### Original profile pipeline – `ml/preprocessing.py`, `learning_style.py`, `peer_recommender.py`, `adaptive_level.py`, `evaluation.py`
The five original scripts' logic, corrected and kept as a command-line pipeline (`python -m ml …`, see [section 14](#14-database-setup-and-initialization)). It works on `sample_data.csv` only and is independent of the web app.

## 7. How the system works

```
Browser (React SPA)
   │  fetch /api/...   (Vite dev server proxies /api -> 127.0.0.1:8000)
   ▼
FastAPI routers  ── services.py ──►  SQLAlchemy ──►  SQLite  (data/app.db)
   │                                                      ▲
   └─► ml_service.py ── load_frames() ── pandas ──────────┘
            │  trains + evaluates models (start-up thread, or POST /api/ml/retrain)
            └─► ml/ package: recsys · knowledge_tracing · learner_state ·
                performance · bandit · style_model · stats
```

1. **Start-up.** On `uvicorn` start the app creates the tables, and, if the database has no courses and `SEED_ON_STARTUP` is true (the default), seeds the sample data. If `ML_TRAIN_ON_STARTUP` is true (default) it trains all models in a background thread (a few seconds to roughly 15 seconds); otherwise the first AI request trains them.
2. **Normal use.** The frontend calls REST endpoints for data and actions. AI endpoints compute per-student outputs from the trained models and the student's current database rows, so recommendations, skills and predictions reflect new activity immediately.
3. **Online learning.** Submitting a quiz also updates the difficulty bandit. The other models are retrained only at start-up or via `POST /api/ml/retrain` (the **Retrain** button).
4. **Too little data.** AI endpoints answer HTTP 503 `ml_insufficient_data` until the database has at least 10 students with 2+ enrolments and 30 quiz attempts.

## 8. Technology stack

| Layer | Technologies (versions as pinned in the repository) |
|---|---|
| **Backend** | Python 3.11–3.15, FastAPI 0.162.0, Uvicorn 0.54.0, SQLAlchemy 2.1.8, python-dotenv 1.2.4, Pydantic (via FastAPI) |
| **Frontend** | React 19.3.1, React Router 7.18.5, Vite 8.3.5, Tailwind CSS 4.3.4, Recharts 3.10.1, lucide-react 1.68.0 |
| **Database** | SQLite (file `data/app.db`) through SQLAlchemy; any SQLAlchemy URL can be set with `DATABASE_URL` (only SQLite is exercised by the project) |
| **Machine learning** | NumPy 2.4.6 / 2.5.4, SciPy 1.17.1 / 1.18.1 (per Python version), pandas 3.1.0, scikit-learn 1.9.1, joblib 1.6.0 |
| **Optional AI** | `anthropic` 2.4.0 (used only if an API key is configured) |
| **Development tools** | pytest 9.0.2, httpx 0.28.1 (FastAPI `TestClient`), Node.js scripts using the Chrome DevTools Protocol for browser tests (no extra npm packages) |

This project does **not** use Flask, Docker, TensorFlow or PyTorch.

## 9. Project architecture

- **`ml/`** – framework-free model code operating on DataFrames. It has no database or web imports, which is why it can be unit-tested with small simulated datasets.
- **`backend/app/`** – FastAPI application factory (`main.py`), settings (`config.py`), engine/session handling (`database.py`), ORM models (`models.py`), Pydantic schemas (`schemas.py`), business rules (`services.py`), uniform JSON errors (`errors.py`), routers, the seed generator, `ml_service.py` (database → models → serving) and `assistant.py`.
- **`frontend/`** – single-page app; every page is lazy-loaded; one fetch wrapper (`src/api/client.js`) talks to the API; context providers hold theme, current student and toasts.
- **Errors** share one shape: `{"error": {"code": "...", "message": "...", "details": [...]}}`. Stack traces are not returned (unexpected errors become `500 internal_error`).

### Database schema (13 tables)

```
students ─┬─< enrollments >── courses ─┬─< lessons
          │        └─< lesson_completions│
          ├─< quiz_attempts >── quizzes ─┘─< quiz_questions
          ├─< activity_logs              courses >─< course_prerequisites >─ courses
          ├─< recommendation_history
          └──0..1── users ──< auth_sessions
```

`users` (logins, role `admin`/`student`, optional link to one student), `auth_sessions` (hashed session tokens) and `recommendation_history` were added by migration `0002`; `courses.is_active` is a new column.
Deleting a student cascades to their enrolments, lesson completions, quiz attempts, activity, recommendation history and login. Details: [docs/API.md](docs/API.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## 10. Complete folder structure

Files tracked in Git are listed. Folders marked *(local only)* are created when you install or run the project and are git-ignored.

```
Personalized-Learning-Path-Recommendation-System/
├── README.md
├── LICENSE                          # MIT (original copyright preserved)
├── .env.example                     # documented backend settings (copy to .env)
├── .gitignore
├── pytest.ini                       # test configuration
├── requirements.txt                 # runtime Python dependencies (pinned)
├── requirements-dev.txt             # + pytest, httpx
├── alembic.ini                      # migration settings (database URL comes from DATABASE_URL)
│
├── backend/
│   └── app/
│       ├── main.py                  # FastAPI app factory + start-up (tables, seeding, ML training)
│       ├── auth.py, security.py     # session/CSRF/role dependencies; Argon2 hashing, password policy, rate limiter
│       ├── migrations.py, migrate.py  # schema state helpers; `python -m backend.app.migrate`
│       ├── create_admin.py          # `python -m backend.app.create_admin` (first administrator)
│       ├── config.py                # settings from environment / .env
│       ├── database.py              # SQLAlchemy engine and session
│       ├── deps.py                  # request-scoped DB session dependency
│       ├── models.py                # ORM tables
│       ├── schemas.py               # request/response validation
│       ├── services.py              # enrolment, lesson, quiz and summary logic
│       ├── errors.py                # error classes and JSON error handlers
│       ├── ml_service.py            # database -> ML models, evaluation, serving
│       ├── assistant.py             # grounded assistant (rules / optional Claude)
│       ├── routers/                 # auth.py, admin.py, students.py, courses.py, learning.py, ml.py, meta.py
│       └── seed/                    # catalog.py (courses/quizzes), generator.py, __main__.py (seed CLI)
│   └── migrations/                  # Alembic: env.py, versions/0001_baseline.py, 0002_authentication.py
│
├── ml/                              # machine-learning package
│   ├── __main__.py, cli.py          # `python -m ml <command>`
│   ├── config.py, schema.py, stats.py
│   ├── recsys.py                    # content-based, collaborative, hybrid, popularity
│   ├── knowledge_tracing.py         # Bayesian Knowledge Tracing
│   ├── learner_state.py             # point-in-time learner features
│   ├── performance.py               # quiz-score prediction
│   ├── bandit.py                    # LinUCB adaptive difficulty
│   ├── style_model.py               # learning-style model (from the database)
│   ├── preprocessing.py, learning_style.py, peer_recommender.py,
│   │   adaptive_level.py, evaluation.py   # original profile pipeline (CSV based)
│   └── legacy/                      # the 5 original scripts (thin wrappers over `python -m ml ...`)
│
├── frontend/
│   ├── package.json, package-lock.json, vite.config.js, index.html
│   ├── .env.example                 # optional frontend settings
│   ├── public/favicon.svg
│   ├── scripts/                     # browser tests: e2e-smoke.mjs, e2e-ai.mjs, e2e-auth.mjs, lib/browser.mjs
│   └── src/
│       ├── main.jsx, App.jsx, index.css
│       ├── api/client.js            # fetch wrapper for every endpoint
│       ├── hooks/useApi.js
│       ├── context/                 # AuthContext, StudentContext, ThemeContext, ToastContext
│       ├── utils/                   # courseStatus.js, format.js
│       ├── pages/                   # Dashboard, MyLearning, CourseInsights, CourseCatalog, Roadmap, Recommendations,
│       │                            # Analytics, ModelEvaluation, Profile, Quiz, Login, Register, NotFound, admin/ (4 pages)
│       └── components/              # layout/, ui/, charts/, course/, learning/, profile/, ai/, auth/
│
├── tests/                           # pytest suite
│   ├── conftest.py, ml_helpers.py
│   ├── test_ml_models.py, test_ml_regression.py, test_models.py,
│   │   test_schema_and_preprocessing.py, test_scripts.py
│   └── backend/                     # API tests: test_api.py, test_ml_api.py, test_ml_integration.py,
│                                    #   test_ml_regression_api.py, test_endpoint_coverage.py, conftest.py, api_helpers.py,
│                                    #   test_auth.py, test_authorization.py, test_course_ml_scope.py, test_migrations.py
│
├── docs/
│   ├── API.md                       # REST reference
│   ├── AUTHENTICATION.md            # roles, sessions, CSRF, migrations, ML scoping
│   ├── ARCHITECTURE.md
│   ├── FRONTEND.md
│   ├── ML_MODELS.md                 # models and measured results
│   ├── PHASE1_ANALYSIS.md           # analysis of the original project
│   └── CHANGELOG.md
│
├── .venv/                           # (local only) Python virtual environment
├── frontend/node_modules/           # (local only) npm packages
├── frontend/dist/                   # (local only) production build output
├── data/                            # sample_data.csv (original dataset, tracked); app.db, backups and processed/ are local only
├── models/                          # trained artefacts of the CSV pipeline (*.pkl, *.csv; small, tracked)
└── reports/                         # (local only) evaluation JSON written by the pipeline/backend
```

## 11. System requirements and prerequisites

| Requirement | Version | Why |
|---|---|---|
| **Python** | 3.11 – 3.15 | Backend and ML. The test suite was run on 3.11; a clean install plus test run was done on 3.15 during development; 3.12–3.14 resolve to prebuilt wheels but were not run through the full suite. |
| **Node.js + npm** | Node 20.19+ or 22.12+ (Vite 8 requirement); developed with Node 24 / npm 11 | Frontend |
| **Git** | any recent version | Cloning |
| **Disk** | a few hundred MB (Python packages + `node_modules`) | |
| **Browser** | any modern browser; Microsoft Edge or Google Chrome is required only for the optional browser tests | |

The project was developed and tested on **Windows 11 with PowerShell**. Commands for macOS/Linux are given below but were **not verified** on those systems. If the project lives in a OneDrive-synced folder it works but is noticeably slower (the test suite took roughly three times longer); a non-synced folder is faster.

Check what you have:

```powershell
python --version
node --version
npm --version
git --version
```

## 12. Installation and setup

Run **all** commands from the **repository root** unless stated otherwise. The frontend commands are the only ones run from `frontend/`.

### 12.1 Clone the repository

```powershell
git clone <repository-url>
cd Personalized-Learning-Path-Recommendation-System
```

Replace `<repository-url>` with the URL of the repository you are cloning, and the folder name if you cloned into a different one.

### 12.2 Create the Python virtual environment

**Windows (PowerShell):**

```powershell
python -m venv .venv
```

Activation is optional because the commands below call the environment's Python directly. If you want to activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell refuses with *"running scripts is disabled on this system"*, skip activation and keep using `.\.venv\Scripts\python.exe` (this avoids changing your execution policy).

**macOS / Linux (not verified):**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 12.3 Install the Python dependencies

For running **and** testing (recommended):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Runtime only (no pytest): `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`.
On macOS/Linux replace `.\.venv\Scripts\python.exe` with `python` (inside the activated environment).

### 12.4 Install the frontend dependencies

In a terminal, from the **`frontend/`** directory:

```powershell
cd frontend
npm install
```

`npm ci` installs exactly what `package-lock.json` specifies and is the better choice for a clean checkout. If PowerShell blocks `npm` for the same script-policy reason, use `npm.cmd` instead.

### 12.5 Configure environment variables (optional)

Every setting has a working default, so you can skip this step. See [section 13](#13-environment-variable-configuration).

```powershell
Copy-Item .env.example .env       # from the repository root; macOS/Linux: cp .env.example .env
```

## 13. Environment variable configuration

Backend settings are read from the process environment or from a `.env` file in the repository root (loaded with python-dotenv). `.env` is git-ignored; never commit it.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | SQLite file `data/app.db` | SQLAlchemy URL, e.g. `sqlite:///C:/path/to/app.db`. Use a separate file for experiments. |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated origins allowed to call the API from a browser. |
| `SEED_ON_STARTUP` | `true` | Create and seed the sample data on start-up when the database has no courses. |
| `SEED_RANDOM_STATE` | `42` | Seed for the synthetic history generator. |
| `ML_TRAIN_ON_STARTUP` | `true` | Train the models in a background thread at start-up (otherwise on the first AI request). |
| `PLRS_DATA_DIR`, `PLRS_MODELS_DIR`, `PLRS_REPORTS_DIR` | `data/`, `models/`, `reports/` | Where the ML code writes its files. |
| `ASSISTANT_PROVIDER` | `auto` | `auto` (Claude if a key is set, else built-in), `rules`, or `claude`. |
| `ANTHROPIC_API_KEY` | *(unset)* | Optional. Enables the Claude-powered assistant. `ANTHROPIC_AUTH_TOKEN` is also recognised. |
| `ANTHROPIC_MODEL` | `claude-opus-5-5` | Claude model used when the key is set. |
| `APP_ENV` | `development` | `production` makes session cookies `Secure` (HTTPS only). |
| `ALLOW_SELF_REGISTRATION` | `false` | Let people create their own student account. Leave off unless needed. |
| `SESSION_TTL_HOURS` | `8` | Session lifetime. |
| `COOKIE_SECURE` | *(from `APP_ENV`)* | Force the `Secure` cookie flag on or off. |
| `MAX_FAILED_LOGINS`, `LOCKOUT_MINUTES` | `5`, `15` | Failed sign-ins before an account is locked, and for how long. |

Frontend (optional; put in `frontend/.env.local`, see `frontend/.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_PROXY_TARGET` | `http://127.0.0.1:8000` | Where the Vite dev/preview server forwards `/api`. Change it if the backend runs on another port. |
| `VITE_API_BASE_URL` | *(empty = same origin)* | Absolute backend URL, only for a production build served separately from the API. |

Browser-test settings: `E2E_EMAIL` and `E2E_PASSWORD` (**required**: an administrator of a *disposable* database), `E2E_URL` (default `http://127.0.0.1:5173`), `E2E_REGISTRATION=1` (when registration is enabled), `E2E_RETRAIN_TIMEOUT_MS`, `E2E_BROWSER` (path to Edge/Chrome), `E2E_SCREENSHOTS` (folder), `E2E_OFFLINE` (`1` to test the backend-down experience).

Setting a variable for one PowerShell session: `$env:CORS_ORIGINS = "http://localhost:5173"`. **Never put API keys in files that are committed**; the assistant works without any key.

## 14. Database setup and initialization

The database is created and filled **automatically** the first time the backend starts (tables via SQLAlchemy, data via the seeder), so no separate step is required.

Manual commands, run from the **repository root**:

```powershell
# create tables and seed only if the database is empty
.\.venv\Scripts\python.exe -m backend.app.seed

# DESTRUCTIVE: drop every table, recreate and reseed (all data is lost)
.\.venv\Scripts\python.exe -m backend.app.seed --reset
```

Stop the backend before `--reset`. Use `DATABASE_URL` to point either command at a different database file.

**Create the first administrator** (there is no default account; the password is typed at a hidden prompt):

```powershell
.\.venv\Scripts\python.exe -m backend.app.create_admin --email you@example.com
```

Sign in with that e-mail, then create student accounts on the **Accounts** page. The seeded sample students have **no login** until an administrator creates one for them (**Students → Login**).

**Upgrading a database created before sign-in existed.** The backend refuses to start on such a database (it never migrates by itself) and tells you what to do:

```powershell
.\.venv\Scripts\python.exe -m backend.app.migrate --dry-run   # rehearsal on a temporary copy; changes nothing
.\.venv\Scripts\python.exe -m backend.app.migrate             # stop the backend first; makes a .bak copy, migrates, verifies row counts
```

The migration is additive (new tables and one new column, existing rows untouched). See [docs/AUTHENTICATION.md](docs/AUTHENTICATION.md#database-schema-and-migrations).

**What the seed contains**

- Hand-written content: 24 courses in 6 topics, 120 lessons, 24 quizzes with 96 questions and answer keys.
- 100 student profiles from `sample_data.csv` (age, learning style, preferred content, daily study time); names and emails are generated placeholders (`@example.edu`).
- **Synthetic** enrolments, lesson completions, quiz attempts (with per-question answers and some retakes), ratings and 12 weeks of activity, generated from a documented learner simulator and anchored to the date of seeding. Students created through the app are marked as real (`is_synthetic = false`).

**Optional: the original CSV-based ML pipeline** (independent of the web app; it writes into `data/processed/`, `models/` and `reports/`):

```powershell
.\.venv\Scripts\python.exe -m ml all
```

Individual steps: `preprocess`, `train-style`, `train-peers`, `train-adaptive`, `evaluate`. The original scripts, kept in `ml/legacy/` (for example `python ml/legacy/Evaluation.py`), call the same commands.

## 15. How to run the backend

**Terminal 1**, from the **repository root** (the command must be run from the root so that the `backend` package is found):

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload
```

`--reload` restarts the server when source files change; leave it out for a steadier process (`.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app`). Another port: add `--port 8001` (and set `VITE_API_PROXY_TARGET` for the frontend). Keep this terminal open.

On the first start it creates `data/app.db`, seeds it and trains the models in the background. (Run `python -m backend.app.create_admin` once so that there is somebody who can sign in.) A successful start prints `Application startup complete.` and `Uvicorn running on http://127.0.0.1:8000`.

**Verify the backend:**

| Check | How |
|---|---|
| Health endpoint | PowerShell: `Invoke-RestMethod http://127.0.0.1:8000/api/health` · bash/cmd: `curl http://127.0.0.1:8000/api/health` → `status: ok` (row counts are shown only to signed-in users) |
| Interactive API docs (Swagger UI) | <http://127.0.0.1:8000/docs> |
| Alternative docs | <http://127.0.0.1:8000/redoc> |
| Models trained | Sign in as administrator and open **Model Evaluation** (`/api/ml/status` is administrator-only) |

(In Windows PowerShell 5.1, `curl` is an alias for `Invoke-WebRequest`; use `curl.exe` or `Invoke-RestMethod`.)

## 16. How to run the frontend

**Terminal 2**, from the **`frontend/`** directory (the backend must already be running):

```powershell
cd frontend
npm run dev
```

Vite prints the address; by default **<http://localhost:5173>**. In development Vite forwards every `/api` request to the backend (`http://127.0.0.1:8000`), so the browser talks to a single origin. If port 5173 is taken, Vite picks the next free port and prints it.

Other npm scripts (all from `frontend/`):

| Command | Purpose |
|---|---|
| `npm run dev` | Development server with hot reload |
| `npm run build` | Production build into `frontend/dist` |
| `npm run preview` | Serve the production build on <http://localhost:4173> (also forwards `/api`) |
| `npm run e2e` | Browser smoke test of the main workflow (see [section 19](#19-how-to-run-automated-tests)) |
| `npm run e2e:ai` | Browser test of the AI/ML features |
| `npm run e2e:auth` | Browser test of sign-in, roles and data isolation |

## 17. How to access and use the application

| What | URL |
|---|---|
| **Web application** | <http://localhost:5173> |
| **Backend API** | <http://127.0.0.1:8000/api> |
| **API documentation** | <http://127.0.0.1:8000/docs> |

**Is it running?** The top bar of the web app shows **API connected** (green dot) when the frontend can reach the backend, and **API offline** with a "Backend not reachable" panel otherwise.

**Sign in first** at <http://localhost:5173/login>. The two roles see separate applications: an administrator sees only the *Administration* menu (admin dashboard, students, courses, accounts, Model Evaluation) and a student sees only the seven student pages. Typing a URL of the other role's pages redirects to your own dashboard, and the API enforces the same rules. If an administrator enabled `ALLOW_SELF_REGISTRATION`, the sign-in page offers **Create a student account**.

Do not experiment on the seeded sample students: create your own student account (**Accounts → New student account**) instead.

| Page | URL path | What it does |
|---|---|---|
| Sign in / Register | `/login`, `/register` | Public. Registration is closed unless enabled |
| Admin dashboard | `/` (administrators) | Totals, popular courses, learners who may need help |
| Admin: Students, Courses, Accounts | `/admin/students`, `/admin/courses`, `/admin/accounts` | Monitor and manage learners, courses and logins |
| Student Dashboard | `/` (students only) | Overview, continue learning, weekly activity, recent quizzes, top recommendations |
| My Learning | `/learning` | Your enrolments: complete lessons, take quizzes, pause, rate |
| Course Insights | `/learning/<course id>` | Guidance for one enrolled course |
| Course Catalog | `/courses` | Search, filter, view details, enrol |
| Learning Roadmap | `/roadmap` | Topic tracks, locks and next steps |
| AI Recommendations | `/recommendations` | Recommendation methods, skill mastery, difficulty, predictions, learning style, assistant |
| Progress & Analytics | `/analytics` | Charts and quiz history over a chosen range |
| Model Evaluation | `/models` (administrators only) | Each model vs. its baseline; retrain |
| Profile | `/profile` | Edit profile, log study time (administrators can also create/delete students) |
| Quiz | `/quiz/<id>` | Opened from My Learning |

### Troubleshooting common startup problems

| Symptom | Likely cause and fix |
|---|---|
| `ModuleNotFoundError: No module named 'backend'` | The command was not run from the repository root. `cd` to the root and run it again. |
| `Activate.ps1 cannot be loaded because running scripts is disabled` | Do not activate; call `.\.venv\Scripts\python.exe` directly. |
| `npm` is blocked by the script policy | Use `npm.cmd` instead of `npm`. |
| `[Errno 10048] ... only one usage of each socket address` | Port 8000 is already in use (maybe another instance). Stop the other process, or start with `--port 8001` and set `VITE_API_PROXY_TARGET=http://127.0.0.1:8001` in `frontend/.env.local`. |
| Web app shows **Backend not reachable** or the Vite terminal prints `ECONNREFUSED` | The backend is not running or runs on a different port. Start it (section 15) and reload the page. |
| Vite refuses to start / `engine` warnings | Node.js is too old. Install Node 20.19+ or 22.12+. |
| AI pages say *Not enough data to train the AI models yet* | The database has fewer than 10 students with 2+ enrolments or fewer than 30 quiz attempts (for example an unseeded or emptied database). Run `python -m backend.app.seed` (or `--reset`). |
| AI cards are empty right after start-up | The models are still training in the background; wait a few seconds or open **Model Evaluation**. |
| `pip install` fails building NumPy/SciPy | Use Python 3.11–3.15; the requirements pin versions that ship prebuilt wheels for those versions. |
| Slow start or slow tests | The folder is probably inside OneDrive. Work from a non-synced folder. |
| Backend stops at start-up with *The database schema needs a migration* | Your `data/app.db` was created before sign-in existed. Run `python -m backend.app.migrate --dry-run`, then `python -m backend.app.migrate` (section 14). |
| *Incorrect e-mail or password* for a seeded student | Seeded students have no login. An administrator must create one (Students → Login). |
| *Too many sign-in attempts* | Rate limit or account lockout (5 failures / 15 minutes). Wait, or an administrator unlocks the account (Accounts → Unlock). Lost the only admin password: `python -m backend.app.create_admin --email ... --reset-password`. |
| Browser tests: *No Edge/Chrome found* | Set `E2E_BROWSER` to the path of a Chromium-based browser. |

## 18. API documentation and important endpoints

Base URL `http://127.0.0.1:8000`. The interactive reference is at `/docs` (Swagger UI) and `/openapi.json`; a written reference is in [docs/API.md](docs/API.md). The API has 47 routes; every route except `/api/health` (limited), `/api/auth/config`, `/api/auth/login` and `/api/auth/register` needs a signed-in session, and state-changing requests need the `X-CSRF-Token` header (see [docs/AUTHENTICATION.md](docs/AUTHENTICATION.md)). The table lists the main groups; [docs/API.md](docs/API.md) lists all of them with the required role.

| Group | Method and path | Description |
|---|---|---|
| **Auth** | `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`, `POST /api/auth/register`, `GET /api/auth/config` | Sessions, current user, optional registration |
| **Admin** | `/api/admin/overview`, `/api/admin/students`, `/api/admin/users…` | Monitoring, accounts (administrators only) |
| **Meta** | `GET /api/health` | Liveness, database check; row counts for signed-in users |
| | `GET /api/meta` | Allowed learning styles, content types, difficulties, topics, statuses |
| **Students** | `GET /api/students` | **Admin.** List (`search`, `learning_style`, `limit` ≤ 100, `offset`) |
| | `POST /api/students` | **Admin.** Create a student |
| | `GET`, `PATCH /api/students/{id}` | The student themself or an admin: read, partially update |
| | `DELETE /api/students/{id}` | **Admin only.** Delete with all history |
| | `GET /api/students/{id}/summary` | Dashboard numbers |
| | `GET /api/students/{id}/progress?weeks=12` | Completion, weekly activity, quiz timeline, score trend, topic scores |
| | `GET /api/students/{id}/quiz-attempts` | Attempt history |
| | `GET`, `POST /api/students/{id}/activity` | Activity log; log self-study minutes |
| **Courses** | `GET /api/courses` | Catalogue (`search`, `topic`, `difficulty`, `content_format`, `limit`, `offset`); archived courses hidden |
| | `GET /api/courses/{id}` | Detail with lessons, prerequisites, quizzes |
| | `POST /api/courses`, `PATCH`, `DELETE /api/courses/{id}` | **Admin.** Create, edit/archive, delete an unused course |
| **Learning** | `GET`, `POST /api/students/{id}/enrollments` | List enrolments; enrol (prerequisites enforced) |
| | `GET`, `PATCH /api/enrollments/{id}` | Read; pause/resume (`status`), rate (`rating`) |
| | `POST /api/enrollments/{id}/lessons/{lesson_id}/complete` | Mark a lesson done (idempotent) |
| | `GET /api/quizzes/{id}` | Questions and options (no answers) |
| | `POST /api/students/{id}/quizzes/{quiz_id}/attempts` | Submit answers; returns score and per-question feedback |
| **AI / ML** | `GET /api/ml/status` | **Admin.** Whether models are trained, training-data provenance |
| | `GET /api/ml/evaluation` | **Admin.** Full evaluation report (all models vs. baselines) |
| | `POST /api/ml/retrain` | **Admin.** Retrain every model on the current database |
| | `GET /api/students/{id}/recommendations?method=hybrid\|content\|collaborative\|popularity&limit=5&course_id=` | Ranked courses with reasons; optional enrolled-course scope |
| | `GET /api/students/{id}/recommendation-history` | What was recommended before |
| | `GET /api/students/{id}/skills?course_id=` | BKT mastery, gaps, untested skills |
| | `GET /api/students/{id}/adaptive-difficulty?course_id=` | Suggested level and per-level expected success |
| | `GET /api/students/{id}/predictions?course_id=` | Predicted quiz score per enrolled course |
| | `GET /api/students/{id}/courses/{course_id}/guidance` | Next steps for one enrolled course |
| | `GET /api/students/{id}/learning-style` | Predicted style, probabilities, `reliable` flag |
| | `POST /api/students/{id}/assistant` | `{"message": "..."}` → grounded answer |

**Status codes:** 401 `not_authenticated`, `invalid_credentials`; 403 `forbidden`, `admin_required`, `csrf_failed`, `origin_not_allowed`, `registration_disabled`; 404 `not_found` (also for another student's records); 429 `rate_limited`; 409 `course_in_use`, `course_archived`, `account_exists`, `email_taken`, `already_enrolled`, `prerequisites_not_met`, `not_enrolled`, `not_completed`, `enrollment_not_active`, `invalid_status_change`; 422 `validation_error`; 503 `ml_insufficient_data`; 500 `internal_error`.

**Example (PowerShell):**

```powershell
# sign in (keeps the session cookie in $s), then call the API with it
$s = $null
$login = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/auth/login" -SessionVariable s `
  -ContentType "application/json" -Body (@{ email = "you@example.com"; password = (Read-Host -AsSecureString | ConvertFrom-SecureString -AsPlainText) } | ConvertTo-Json)
Invoke-RestMethod "http://127.0.0.1:8000/api/courses?topic=Statistics&limit=3" -WebSession $s
Invoke-RestMethod "http://127.0.0.1:8000/api/students/7/recommendations?method=hybrid&limit=3" -WebSession $s
# state-changing calls also need:  -Headers @{ "X-CSRF-Token" = $login.csrf_token }
```

## 19. How to run automated tests

**Python tests** – run from the **repository root**; no servers need to be running, and every test uses a temporary database, so your `data/app.db` is not touched:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

The suite has 216 tests (unit tests of the ML modules with simulated data, API tests, end-to-end API/ML integration, regression tests for the knowledge-tracing and score-prediction fixes, and tests for migrations, authentication, authorisation, student data isolation and course-scoped ML). The API tests run as an authenticated administrator or student. Expect several minutes (a lot longer on a slow or OneDrive-synced disk). Useful variants:

```powershell
.\.venv\Scripts\python.exe -m pytest -q                      # quieter output
.\.venv\Scripts\python.exe -m pytest tests/test_ml_regression.py
.\.venv\Scripts\python.exe -m pytest -k bkt
```

**Browser tests** (optional) drive a real headless Edge/Chrome through the UI. They need the backend and the frontend dev server running, they sign in as an administrator (`E2E_EMAIL`, `E2E_PASSWORD`), and they **create and delete test students/accounts in whichever database the backend is using**. Run them against a disposable database (start the backend with `DATABASE_URL` pointing at a new file and create an administrator there with `python -m backend.app.create_admin`), not against data you care about:

```powershell
cd frontend
$env:E2E_EMAIL = "admin@example.com"; $env:E2E_PASSWORD = "<the disposable admin's password>"
npm run e2e         # main workflow
npm run e2e:ai      # AI/ML features through the UI
npm run e2e:auth    # sign-in, roles, data isolation
```

## 20. How to build the frontend for production

From the **`frontend/`** directory:

```powershell
npm ci
npm run build       # output: frontend/dist
npm run preview     # optional: serve the build at http://localhost:4173
```

`npm run preview` also forwards `/api` to the backend, so start the backend first. The repository contains **no Dockerfile or deployment configuration**, and deploying the backend and a production web server is not covered or tested. If you host the built files separately from the API, build with `VITE_API_BASE_URL` set to the backend's absolute URL and add the site's origin to the backend's `CORS_ORIGINS`.

## 21. Machine learning model information

All models are trained on the project's own database. On a fresh checkout that data is **100 seeded students whose histories are synthetic**, so metrics describe how well a model recovers *simulated* behaviour, not real-world effectiveness. The API and UI state this next to every model output.

Every comparison uses a paired bootstrap 95% confidence interval; a model counts as better only if the interval lies entirely above zero. Results of the latest run on the seeded data (rounded; exact numbers change slightly with the data and are always on the **Model Evaluation** page and in `GET /api/ml/evaluation`):

| Model | Evaluation protocol | Result vs. baseline |
|---|---|---|
| Course recommendations (hybrid) | leave-last-out, held-out students | NDCG@5 ≈ 0.72 vs. ≈ 0.70 for popularity: **not significant** |
| Skill mastery (BKT) | 70/30 student split, each answer predicted from earlier answers | AUC ≈ 0.63, log-loss ≈ 0.49; log-loss gain over the best baseline **not significant** |
| Quiz-score prediction | chronological split, last 20% of attempts | MAE ≈ 15.9 vs. ≈ 17.3 (training mean / student's own average): **significant** improvement |
| Adaptive difficulty (LinUCB) | chronological split | Brier gain over per-level average **not significant**; the policy-value replay is biased and indicative only |
| Learning style (decision tree) | 5-fold nested CV | ≈ 23% accuracy vs. 32% majority baseline: **not reliable** |

Further detail and the history of these results: [docs/ML_MODELS.md](docs/ML_MODELS.md) (some figures there differ from the table above by a few thousandths because they come from an earlier run).

**About `sample_data.csv`.** The original CSV has no learnable signal: its columns behave like independent random draws, and no classifier beats the majority baseline on it (measured in [docs/PHASE1_ANALYSIS.md](docs/PHASE1_ANALYSIS.md)). That is why the web app uses a generated course catalogue and simulated learner histories.

**Retraining.** Models are trained at back-end start-up (if `ML_TRAIN_ON_STARTUP` is true) and when you press **Retrain on current data** or call `POST /api/ml/retrain`. Students you create are included in later training runs. The evaluation report is also written to `reports/ml_evaluation.json`.

## 22. Sample workflow

1. Create the first administrator ([section 14](#14-database-setup-and-initialization)), start the backend and the frontend ([sections 15 and 16](#15-how-to-run-the-backend)), open <http://localhost:5173> and sign in. Wait for **API connected**.
2. As the administrator open **Accounts → New student account** and create a student (name, a valid e-mail, age 10-100, a temporary password), then **Sign out** and sign in as that student. (With `ALLOW_SELF_REGISTRATION=true` a student can instead use **Create a student account** on the sign-in page.)
3. Open **Course Catalog**, click *Python Fundamentals* and choose **Enroll**. Locked courses explain which prerequisites are missing.
4. In **My Learning**, press **Complete next lesson** until all five lessons are done; the course completes automatically.
5. Click **Take quiz**, answer every question and **Submit answers**. You get a score, a pass/fail result and an explanation per question; **Retake** is available.
6. Open **My Learning → Insights** on the course for guidance limited to that course. Open **AI Recommendations**: the hybrid list now excludes the finished course and includes courses it unlocked; switch between the four methods; check **Skill mastery**, **Adaptive difficulty** and **Predicted quiz scores**, which now reflect your quiz; ask the assistant "What should I study next?".
7. Open **Progress & Analytics** for your activity and score history. As the administrator, open **Students** to see this learner's enrolments and averages, and **Model Evaluation** to see how each model compares with its baseline (try **Retrain on current data**).
8. Optional cleanup: as the administrator, **Students → delete** removes your test student, their login and all their history.

## 23. Known issues and limitations

**Verified defects** (found during manual QA testing; not yet fixed):

- **Analytics trend caption:** when quiz attempts are made within minutes of each other, the score-trend line can show an absurd value such as "+31721255.76 points per week".
- **Mobile layout (375 px):** the AI Recommendations and Model Evaluation pages are wider than the screen (the recommendation method tabs and the evaluation tables are not contained), so the page scrolls sideways; Analytics does the same with dense data, and the Dashboard overflows by about 4 px. Tablet and desktop widths are unaffected.
- **Insufficient-data message:** when there is too little data to train, the AI page shows a "Models are training in the background" banner that never resolves, plus red "Something went wrong" cards that actually contain the explanation.
- **Profile hint text:** the learning-style field still says "An ML-predicted style is added in Phase 5."
- **Resume:** a paused course has no Resume button in My Learning; it can be resumed from its dialog in the Course Catalog.
- **Invalid quiz URL:** `/quiz/abc` shows a generic "Request validation failed" instead of "not found".
- **Small targets:** several stand-alone text links (for example "View all", "Details") are shorter than 24 px.

**Model limitations**

- Histories are synthetic and most models do not significantly beat simple baselines (table above).
- BKT credits recent correct answers: a learner who fails a quiz and then answers everything correctly on the immediate retake is judged to have learned the skill, even though overall accuracy is 50%. Repeated *wrong* answers do keep mastery below the threshold.
- The "likely / uncertain / at risk" hint on score predictions is based on the prediction plus or minus the model's average error, so a clearly weak learner can be labelled *uncertain* when the range straddles the pass mark.
- The difficulty bandit can suggest *Advanced* to a new learner because it explores arms with little data (the card says so). There are only about 8 Advanced training attempts in the seeded data.
- The learning-style model is flagged unreliable; the app uses the self-reported style.
- Models are retrained only at start-up or on request; deleting a student does not retrain them.

**Product and environment limitations**

- Sign-in is a first implementation: no e-mail verification, no password-reset e-mail, no multi-factor authentication, no audit log, and the login rate-limit counters live in one process (details in [docs/AUTHENTICATION.md](docs/AUTHENTICATION.md#known-limitations)).
- The web app gives administrators no way to act as a student, but the API still lets an administrator call the per-student endpoints (for example to submit a quiz for a student); the monitoring pages only read.
- Seeded students have no login until an administrator creates one.
- Courses added by an administrator are only recommended after the models are retrained.
- The browser tests create and delete students and accounts in the connected database.
- Developed and tested on Windows 11. Linux/macOS commands, Firefox and Safari, screen-reader behaviour, performance under load and Claude-assistant mode with a real API key were not tested.
- No continuous-integration configuration is included yet.

## 24. Security considerations

This is a local demonstration and should **not** be exposed to the internet as is.

- **Authentication and roles.** Every API route except the health probe, `GET /api/auth/config`, login and (when enabled) register requires a session. Passwords are hashed with Argon2id; session cookies are `HttpOnly` and `SameSite=Lax` (and `Secure` when `APP_ENV=production`); only a hash of each session token is stored; state-changing requests need a per-session CSRF token and an allowed `Origin`. Students can reach only their own records (other students' ids answer `404`), only administrators can list, create or delete students, manage courses and accounts, and open Model Evaluation. Login attempts are rate limited and accounts lock after repeated failures. This has **not been independently security-reviewed**; see [docs/AUTHENTICATION.md](docs/AUTHENTICATION.md) for the model and its limitations.
- **Account creation.** There is no default account. `ALLOW_SELF_REGISTRATION` is `false` by default; when enabled, a registration always creates a new student profile and can never attach to an existing one. Only an administrator can link a login to an existing (seeded) student.
- **Student deletion.** `DELETE /api/students/{id}` is administrator-only and permanently removes the student with their enrolments, attempts, activity, recommendation history and login. There is still no soft delete or undo.
- **CORS.** By default only `http://localhost:5173` and `http://127.0.0.1:5173` may call the API from a browser (`CORS_ORIGINS`), with credentials, for the methods GET/POST/PATCH/DELETE and the `Content-Type` and `X-CSRF-Token` headers. A wildcard origin is refused at start-up. During development the Vite proxy makes requests same-origin, so CORS rarely matters locally. Add origins only deliberately.
- **Network exposure.** Uvicorn binds to `127.0.0.1` by default. Do not start it with `--host 0.0.0.0` on an untrusted network.
- **Input validation.** Request bodies and parameters are validated with Pydantic (types, ranges, lengths, e-mail pattern, pagination limits); SQL is issued through SQLAlchemy; unexpected errors return a generic `500 internal_error` without a stack trace. Login and registration are rate limited; there is no general rate limiting, and the app does not provide HTTPS itself (use a reverse proxy and `APP_ENV=production` if you expose it).
- **Secrets.** No keys or passwords are stored in the repository. Provide `ANTHROPIC_API_KEY`, if you use it, through the environment or an untracked `.env`. **If a key is set, the learner's progress and model outputs are sent to Anthropic's API** to produce the assistant's answers; leave it unset to keep everything local.
- **Pickled models.** The optional CSV pipeline stores models with joblib/pickle in `models/`. Only load pickle files you created yourself.
- **Dev tooling.** `uvicorn --reload` and the Vite dev server are development servers.

## 25. Future improvements

- Fix the verified defects listed in [section 23](#23-known-issues-and-limitations).
- Password-reset by e-mail, multi-factor authentication, an audit log, soft deletion for destructive actions, and an independent security review.
- Real learner data in place of the synthetic histories, and re-evaluation of every model on it.
- Treat answers on retakes as weaker evidence in knowledge tracing; replace the error-band prediction hint with a pass probability.
- Containerisation, a deployment guide, and continuous integration (tests and build on every push).
- Cross-browser and accessibility testing.

## 26. Contributing guidelines

Contributions are welcome.

1. Fork the repository and create a branch (`git checkout -b feature/short-description`).
2. Set up the project as described in [section 12](#12-installation-and-setup) and run the tests before changing anything: `.\.venv\Scripts\python.exe -m pytest`.
3. Keep changes focused; add or update tests next to the code you change (`tests/` for Python; the `frontend/scripts/` browser tests for UI flows).
4. Run the full test suite and `npm run build` before opening a pull request.
5. Never commit `.env`, API keys, database files or `reports/` output (git-ignored).
6. Describe what changed and why in the pull request; link evidence (test output, evaluation numbers) for model changes, and report results against the baselines.

## 27. License and original project attribution

This project is released under the **MIT License**; see [LICENSE](LICENSE). The licence file keeps the original copyright notice: *Copyright (c) 2024 Christian Amezcua*.

**Original project.** This repository is based on [chrisamz/Personalized-Learning-Path-Recommendation-System](https://github.com/chrisamz/Personalized-Learning-Path-Recommendation-System) by Christian Amezcua, which consisted of five scripts (`Data-Preprocessing.py`, `Learning-Style-Classification.py`, `Recommendation-Algorithm.py`, `Adaptive-Learning-System.py`, `Evaluation.py`) and the dataset `sample_data.csv`. Those scripts are retained as thin wrappers around the corrected implementations in `ml/`, and `sample_data.csv` is unchanged.

**What was changed.** The documented analysis of the original code is in [docs/PHASE1_ANALYSIS.md](docs/PHASE1_ANALYSIS.md): the adaptive model had target leakage, the reinforcement-learning draft was broken, and the recommender returned similar *students* (including the query student itself). These were fixed, and the following was added: the FastAPI backend and database, the course catalogue and seed generator, the React frontend, the course-level recommenders, knowledge tracing, score prediction, the difficulty bandit, the assistant, evaluation against baselines, and the test suite. The full history is in [docs/CHANGELOG.md](docs/CHANGELOG.md).

**Note on the original README.** The original README described Flask, Docker, TensorFlow/PyTorch, Jupyter notebooks and "high performance metrics". None of that was backed by code or measurements in the repository, and it has been removed from this README.

## 28. Author / project credits

- **Original author:** Christian Amezcua (MIT-licensed original project, linked above).
- **v2 extension (backend, frontend, ML modules, tests and documentation):** Amer, as recorded in the Git history of the `upgrade/v2` branch.

Built with open-source software: FastAPI, SQLAlchemy, scikit-learn, pandas, NumPy, SciPy, React, Vite, Tailwind CSS and Recharts.



05/11/26
Credentials in the README (all labelled LOCAL DEMO ONLY)

┌─────────────────────────────┬──────────────────────────────┬────────────────────────────────────────────────────────────────────────────────────────┐
│            Role             │            E-mail            │                                        Password                                        │
├─────────────────────────────┼──────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
│ Admin                       │ admin@plrs-test.example      │ Not documented. The admin isn't in the database yet, so the README gives the           │
│                             │                              │ hidden-prompt create_admin command                                                     │
├─────────────────────────────┼──────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
│ Student 1: Mia Chen         │ mia.chen.7@example.edu       │ Quartz-Falcon-Ridge-91                                                                 │
│ (existing, #7)              │                              │                                                                                        │
├─────────────────────────────┼──────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
│ Student 2: Priya Nair (new, │ priya.nair@plrs-test.example │ Cobalt-Meadow-Harbor-58                                                                │
│  #101)                      │                              │                                                                                        │
└─────────────────────────────┴──────────────────────────────┴────────────────────────────────────────────────────────────────────────────────────────┘

---

## 29. Accounts, course selection and course-access approval

### Student accounts (sign in at `/login`)

These ten learners come from the generated sample data. Their quiz history and courses are kept; each now has a login.
The other 90 sample learners have no login. New students register at `/register`.

| # | Name | Email | Password |
|---|------|-------|----------|
| 1 | Aarav Costa | aarav.costa.1@example.edu | `2IVz4O1b45mF9YY9` |
| 2 | Sara Walker | sara.walker.2@example.edu | `qOEaZ_LSPR-2gzoE` |
| 3 | Priya Patel | priya.patel.3@example.edu | `o8jIFwk2StYrNlPu` |
| 4 | Daniel Ivanova | daniel.ivanova.4@example.edu | `epo0XR7O6GHw65yI` |
| 5 | Fatima Khan | fatima.khan.5@example.edu | `P9kDGPmpvGjKDMAp` |
| 6 | Noah Moreau | noah.moreau.6@example.edu | `4v5l1wWDIQV68qm1` |
| 7 | Mia Chen | mia.chen.7@example.edu | `bi1ff1efeVsbBX9z` |
| 8 | Daniel Hughes | daniel.hughes.8@example.edu | `5SECS4w5thw3f8lw` |
| 9 | Meera Walker | meera.walker.9@example.edu | `ToDuvI2rt3CbgXDR` |
| 10 | Sofia Kim | sofia.kim.10@example.edu | `z1aX8jCV2axXu6P-` |

### For students: choosing a course and learning

1. Sign in at `/login` (or register at `/register`).
2. Open **Course Catalog**. Search or filter by topic, level or format, and click a course to see its lessons,
   prerequisites and quiz.
3. Click **Request enrollment**. Courses whose prerequisites you have not completed are locked.
4. Your request shows as **Waiting for approval** under **My Learning -> Requests**. You can withdraw it from there while
   it is still pending.
5. After an administrator approves it, the course appears under **My Learning -> In progress**. A rejected request shows
   the administrator's reason, and you can send a new one.
6. Study with **Complete next lesson**, then take the course quiz. Your scores and progress feed **Progress & Analytics**,
   **Learning Roadmap** and **AI Recommendations**.

### For the administrator: approving course access

1. Sign in at `/admin/login` (the "Admin login" link on the sign-in page). Student accounts are refused there.
2. Open **Enrollment requests**. The **Pending** tab lists each student, their course and the request date.
3. Click **Approve** to enrol the student (prerequisites are checked again), or **Reject** with an optional reason that
   the student sees.
4. The admin dashboard shows registered students, pending/approved/rejected counts, students enrolled per course, and
   each student's progress and scores.

### Admin login

| | |
|---|---|
| Sign-in page | `/admin/login` |
| Email | `admin@pathwise.local` |
| Password | the password you set with `python -m backend.app.create_admin` (never stored in the repository) |
