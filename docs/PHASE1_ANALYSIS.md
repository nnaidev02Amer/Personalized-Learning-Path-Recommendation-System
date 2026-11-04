# Phase 1 – Analysis of the original project

Snapshot analysed: upstream commit `3c9a8ae` plus local edits, preserved at git
tag `baseline-local-2026-11-04`.

## Dataset (`sample_data.csv`)

100 students, 8 columns: `StudentID, Age, LearningStyle, Progress,
CompletedCourses, AverageScore, PreferredContent, SessionTime`. No missing
values, no duplicates. There is **no course catalogue and no student–course
interaction data**.

### The data carries no learnable signal

Measured with 5-fold stratified cross-validation:

| Model predicting `LearningStyle` | CV accuracy |
|---|---|
| Majority-class baseline | **0.32** |
| Decision Tree | 0.20 |
| Random Forest | 0.27 |
| Logistic Regression | 0.26 |

Statistical tests against `LearningStyle`: ANOVA p-values for every numeric
feature are 0.27–0.97, chi² for `PreferredContent` p = 0.95. All pairwise
feature correlations are |r| < 0.15. The columns behave as independent random
draws, so no algorithm can be expected to beat the baseline on this file. This
is why Phase 3 adds a documented synthetic data generator with real structure.

## Issues found

1. Adaptive model: target leakage – its label is derived from `Progress` and
   `AverageScore`, which are also its inputs (RandomForest reached only 0.77
   CV accuracy at re-learning that formula). Labelling a single student with
   `rank(pct=True)` always gave the top level.
2. Not reinforcement learning: the DQN draft was commented out and broken
   (deprecated `lr=`, wrong Bellman target).
3. Recommender returned similar *students*, included the query student itself
   as the top result, returned n+1 results, and printed standardised values
   (e.g. `Progress: -0.959`).
4. No collaborative / hybrid filtering possible without interaction data.
5. Scaler/imputer fitted on all rows before the train/test split; features
   scaled twice.
6. K-Means clusters computed then discarded; k = 4 not validated.
7. `avg_performance` duplicated `AverageScore`; `StudentID` became a float.
8. `load_models()` removed – `classify_new_student` unusable after restart.
9. Hyphenated script names cannot be imported by a backend.
10. Hard-coded relative paths – only worked from the repository root.
11. `Evaluation.py` re-created the test split by seed; KMeans and adaptive
    model not evaluated.
12. README referenced files and commands that do not exist and claimed
    unmeasured "high performance metrics".
13. TensorFlow installed but unused; no `requirements.txt`; versions unpinned.
