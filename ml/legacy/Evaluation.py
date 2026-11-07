"""Evaluate all models against baselines and write reports/evaluation_report.json.

Thin entry point kept for backward compatibility. The implementation lives in
`ml/evaluation.py`; this script is equivalent to `python -m ml evaluate`
and can be run from any directory.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ml.evaluation import ModelEvaluation  # noqa: E402,F401  (re-exported)
from ml.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["evaluate", *sys.argv[1:]]))
