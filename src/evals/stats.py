"""Statistical helpers — bootstrap CI + paired bootstrap test.

Not wired into the M1 report (single-seed runs); defined now so M2 multi-seed
comparisons don't need new plumbing.
"""

from __future__ import annotations

import numpy as np


def bootstrap_ci(
    values: list[float],
    *,
    alpha: float = 0.05,
    n_resamples: int = 10_000,
    seed: int = 42,
) -> tuple[float, float]:
    """Return the (lo, hi) confidence interval for the mean of `values`."""
    if not values:
        return (0.0, 0.0)
    rng = np.random.default_rng(seed)
    arr = np.asarray(values, dtype=float)
    n = arr.size
    resamples = rng.choice(arr, size=(n_resamples, n), replace=True).mean(axis=1)
    lo = float(np.percentile(resamples, 100 * (alpha / 2)))
    hi = float(np.percentile(resamples, 100 * (1 - alpha / 2)))
    return lo, hi


def paired_bootstrap_pvalue(
    a: list[float],
    b: list[float],
    *,
    n_resamples: int = 10_000,
    seed: int = 42,
) -> float:
    """Two-sided p-value for H0: mean(a) == mean(b), paired observations."""
    if len(a) != len(b):
        raise ValueError("paired bootstrap requires equal-length samples")
    if not a:
        return 1.0
    rng = np.random.default_rng(seed)
    diffs = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    n = diffs.size
    observed = float(diffs.mean())
    centered = diffs - observed
    resamples = rng.choice(centered, size=(n_resamples, n), replace=True).mean(axis=1)
    p = float((np.abs(resamples) >= abs(observed)).mean())
    return p
