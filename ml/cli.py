"""Command-line interface: ``python -m ml <command>``.

The five original root scripts call these same commands, so
``python Learning-Style-Classification.py`` and
``python -m ml train-style`` do exactly the same thing.
"""

from __future__ import annotations

import argparse
import sys
import warnings

from ml import config


def _header(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def preprocess(args) -> None:
    from ml import preprocessing
    result = preprocessing.run(args.input)
    print("\nStudent data preprocessing completed successfully!")
    print("Total student records:", result["records"])
    print("Clean data (original units):", result["clean_path"])
    print("Standardised data:          ", result["preprocessed_path"])
    print("\nProcessed data preview:")
    print(result["preview"])


def train_style(args) -> None:
    from ml import learning_style
    classifier = learning_style.run(args.input)
    m, seg = classifier.metrics, classifier.cluster_report
    _header("K-Means Segmentation")
    print(f"Clusters chosen by silhouette: {seg['n_clusters']} "
          f"(silhouette {seg['silhouette']}; scores by k: {seg['silhouette_by_k']})")
    _header("Decision Tree Classifier Results")
    print("Best parameters (5-fold CV on train):", m["best_params"])
    print(f"CV accuracy:        {m['cv_accuracy_mean']} +/- {m['cv_accuracy_std']}"
          f"  (majority baseline {m['baseline_cv_accuracy']})")
    print(f"Held-out accuracy:  {m['test_accuracy']}"
          f"  (majority baseline {m['baseline_test_accuracy']}, chance {m['chance_accuracy']})")
    print("Held-out F1 (weighted):", m["test_f1_weighted"])
    if not m["beats_baseline"]:
        print("NOTE: the classifier does not beat the majority-class baseline on this data.")
    print("\nModels saved to:", config.models_dir())
    print("Metrics saved to:", config.reports_dir() / learning_style.METRICS_FILE)


def train_peers(args) -> None:
    from ml import peer_recommender
    recommender, student, peers = peer_recommender.run(args.input)
    print("Recommendation model trained successfully!")
    _header(f"Most similar students to StudentID {int(student['StudentID'])} "
            f"({student['LearningStyle']}, prefers {student['PreferredContent']})")
    for peer in peers:
        print(peer)
    _header("Suggested content formats (from similar peers)")
    for item in recommender.suggest_content(peers):
        print(f"{item['content_type']:<10} {item['share']:.0%}")


def train_adaptive(args) -> None:
    from ml import adaptive_level
    _, assessment = adaptive_level.run(args.input)
    print("Adaptive learning-level policy fitted and saved.")
    _header("Adaptive Learning Recommendation (first student)")
    print(assessment["action"])
    print(f"Performance percentile: {assessment['performance_percentile']:.0%} "
          f"(progress {assessment['progress_percentile']:.0%}, "
          f"score {assessment['score_percentile']:.0%})")


def evaluate(args) -> None:
    from ml.evaluation import REPORT_FILE, ModelEvaluation
    report = ModelEvaluation().run_all()
    for section in ("learning_style_classification", "peer_recommender", "adaptive_level_policy"):
        _header(section.replace("_", " ").upper())
        for key, value in report[section].items():
            print(f"{key}: {value}")
    print("\nReport saved to:", config.reports_dir() / REPORT_FILE)
    print("WARNING:", report["dataset"]["warning"])


def run_all(args) -> None:
    for step in (preprocess, train_style, train_peers, train_adaptive, evaluate):
        step(argparse.Namespace(input=args.input if step is preprocess else None))


COMMANDS = {
    "preprocess": (preprocess, "Clean and standardise sample_data.csv"),
    "train-style": (train_style, "Train the learning-style classifier"),
    "train-peers": (train_peers, "Fit the similar-student recommender"),
    "train-adaptive": (train_adaptive, "Fit the learning-level policy"),
    "evaluate": (evaluate, "Evaluate all models and write a JSON report"),
    "all": (run_all, "Run every step in order"),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ml", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name, (func, help_text) in COMMANDS.items():
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--input", default=None, help="input CSV (defaults depend on the step)")
        p.set_defaults(func=func)
    args = parser.parse_args(argv)
    warnings.filterwarnings("ignore", category=UserWarning)
    try:
        args.func(args)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}. Run the earlier pipeline steps first "
              "(e.g. `python -m ml all`).", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"ERROR: invalid data: {exc}", file=sys.stderr)
        return 1
    return 0
