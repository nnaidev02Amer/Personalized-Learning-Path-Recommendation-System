"""Paired bootstrap confidence intervals for model-vs-baseline comparisons."""

from __future__ import annotations

import numpy as np


def paired_bootstrap(model_values, baseline_values, *, higher_is_better: bool, n_boot: int = 2000,
                     random_state: int = 42) -> dict:
    """Bootstrap the mean per-item improvement of model over baseline.

    Returns the mean improvement (positive = model better), its 95% CI and
    ``significant`` = the CI excludes zero.
    """
    m = np.asarray(model_values, float)
    b = np.asarray(baseline_values, float)
    diff = (m - b) if higher_is_better else (b - m)
    rng = np.random.default_rng(random_state)
    idx = rng.integers(0, len(diff), size=(n_boot, len(diff)))
    boots = diff[idx].mean(axis=1)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return {"improvement": round(float(diff.mean()), 4), "ci95": [round(float(lo), 4), round(float(hi), 4)],
            "significant": bool(lo > 0), "n": int(len(diff))}
