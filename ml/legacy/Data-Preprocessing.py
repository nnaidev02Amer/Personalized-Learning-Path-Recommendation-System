"""Data preprocessing: clean and standardise the student dataset.

Thin entry point kept for backward compatibility. The implementation lives in
`ml/preprocessing.py`; this script is equivalent to `python -m ml preprocess`
and can be run from any directory.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ml.preprocessing import DataPreprocessing  # noqa: E402,F401  (re-exported)
from ml.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["preprocess", *sys.argv[1:]]))
