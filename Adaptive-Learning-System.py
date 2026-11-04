"""Adaptive learning-level policy (percentile-based; RL is added in Phase 3).

Thin entry point kept for backward compatibility. The implementation lives in
`ml/adaptive_level.py`; this script is equivalent to `python -m ml train-adaptive`
and can be run from any directory.

The earlier commented-out DQN draft (broken: deprecated `lr=` argument and a
wrong Bellman target) and the leaky RandomForest version are preserved in git
history at tag `baseline-local-2026-11-04`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ml.adaptive_level import AdaptiveLearningSystem  # noqa: E402,F401  (re-exported)
from ml.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["train-adaptive", *sys.argv[1:]]))
