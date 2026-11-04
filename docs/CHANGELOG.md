# Changelog

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
