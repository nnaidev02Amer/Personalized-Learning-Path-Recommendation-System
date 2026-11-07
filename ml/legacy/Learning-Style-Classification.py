"""Learning-style classification: K-Means segmentation + Decision Tree.

Thin entry point kept for backward compatibility. The implementation lives in
`ml/learning_style.py`; this script is equivalent to `python -m ml train-style`
and can be run from any directory.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ml.learning_style import LearningStyleClassification  # noqa: E402,F401  (re-exported)
from ml.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["train-style", *sys.argv[1:]]))
