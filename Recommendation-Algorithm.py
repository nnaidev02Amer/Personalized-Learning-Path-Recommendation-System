"""Similar-student recommender (cosine k-NN) with content-format suggestions.

Thin entry point kept for backward compatibility. The implementation lives in
`ml/peer_recommender.py`; this script is equivalent to `python -m ml train-peers`
and can be run from any directory.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ml.peer_recommender import RecommendationAlgorithm  # noqa: E402,F401  (re-exported)
from ml.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["train-peers", *sys.argv[1:]]))
