# Architecture

## Target layout

```
├── ml/                     # importable ML package (no web code)
│   ├── config.py           # paths (env-overridable), seeds          [Phase 2]
│   ├── schema.py           # column definitions + input validation    [Phase 2]
│   ├── preprocessing.py    # cleaning / standardisation               [Phase 2]
│   ├── learning_style.py   # K-Means segmentation + Decision Tree     [Phase 2]
│   ├── peer_recommender.py # similar-student k-NN                     [Phase 2]
│   ├── adaptive_level.py   # percentile learning-level policy         [Phase 2]
│   ├── evaluation.py       # baseline-aware evaluation report         [Phase 2]
│   ├── cli.py              # `python -m ml <command>`                 [Phase 2]
│   ├── recsys.py           # content-based, item-kNN, hybrid, popularity [Phase 5]
│   ├── knowledge_tracing.py# Bayesian Knowledge Tracing                [Phase 5]
│   ├── bandit.py           # LinUCB adaptive difficulty               [Phase 5]
│   ├── performance.py      # quiz-score prediction (gradient boosting) [Phase 5]
│   ├── style_model.py      # learning style from behaviour            [Phase 5]
│   ├── learner_state.py    # point-in-time learner features           [Phase 5]
│   └── stats.py            # paired bootstrap CIs                     [Phase 5]
├── backend/app/            # FastAPI + SQLAlchemy (SQLite)            [Phase 3]
│   ├── ml_service.py       # DB → ml/ models, evaluation, serving       [Phase 5]
│   └── assistant.py        # grounded assistant, optional Claude API   [Phase 5]
├── frontend/               # React + Vite + Tailwind + Recharts       [Phase 4] (see FRONTEND.md)
├── tests/                  # pytest suite
├── docs/                   # analysis, architecture, changelog
├── data/                   # sample_data.csv (original, never modified); app.db / processed/ are generated
├── models/                 # trained artefacts (small, tracked)
├── reports/                # evaluation JSON (git-ignored)
└── ml/legacy/*.py          # 5 original entry points → thin wrappers over ml/
```

## Principles

* **One source of truth per concern.** Root scripts, the CLI and (later) the
  API all call the same functions in `ml/`.
* **Leakage-safe training.** All scaling/encoding lives inside sklearn
  `Pipeline`s fitted on training rows only; held-out IDs are persisted and
  re-used by evaluation.
* **Every metric next to a baseline.** Reports state when a model does not
  beat the baseline instead of hiding it.
* **Validated inputs.** `ml.schema.validate_students` guards every model entry
  point; the API will map `ValidationError` to HTTP 422.
* **Location-independent.** Paths resolve from the repo root and can be
  redirected with `PLRS_DATA_DIR`, `PLRS_MODELS_DIR`, `PLRS_REPORTS_DIR`.

## Student-profile pipeline (Phase 2)

```
data/sample_data.csv
   │  preprocessing.run()
   ├─► data/processed/clean_student_data.csv          (original units – model input)
   └─► data/processed/preprocessed_student_data.csv   (standardised – analysis/legacy)
          │
          ├─ learning_style.run()   → models/learning_style_pipeline.pkl, kmeans_pipeline.pkl
          │                            reports/learning_style_metrics.json (incl. test IDs)
          ├─ peer_recommender.run() → models/recommendation_*.pkl/.csv
          ├─ adaptive_level.run()   → models/adaptive_learning_model.pkl
          └─ evaluation             → reports/evaluation_report.json
```
