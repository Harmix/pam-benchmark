"""Statistical helpers — used by every multi-seed comparison from M2 onward."""

from __future__ import annotations

import pytest

from evals.stats import bootstrap_ci, paired_bootstrap_pvalue


def test_bootstrap_empty_returns_zeros():
    assert bootstrap_ci([]) == (0.0, 0.0)


def test_bootstrap_ci_contains_mean_for_low_variance_sample():
    values = [0.5] * 50  # zero variance
    lo, hi = bootstrap_ci(values, seed=1)
    assert lo <= 0.5 <= hi
    assert hi - lo < 0.01  # extremely tight CI


def test_bootstrap_ci_widens_with_variance():
    rng_a = [0.4, 0.5, 0.6] * 20
    rng_b = [0.0, 0.5, 1.0] * 20
    lo_a, hi_a = bootstrap_ci(rng_a, seed=1)
    lo_b, hi_b = bootstrap_ci(rng_b, seed=1)
    assert (hi_b - lo_b) > (hi_a - lo_a)


def test_bootstrap_ci_is_seed_deterministic():
    vs = [0.1, 0.4, 0.5, 0.9, 0.2] * 10
    assert bootstrap_ci(vs, seed=42) == bootstrap_ci(vs, seed=42)


def test_paired_pvalue_identical_samples_is_one():
    same = [0.5, 0.7, 0.3] * 10
    p = paired_bootstrap_pvalue(same, same, seed=1)
    assert p == pytest.approx(1.0)


def test_paired_pvalue_large_gap_is_small():
    a = [1.0] * 30
    b = [0.0] * 30
    p = paired_bootstrap_pvalue(a, b, seed=1)
    assert p < 0.01


def test_paired_pvalue_mismatched_lengths_raises():
    with pytest.raises(ValueError):
        paired_bootstrap_pvalue([0.1, 0.2], [0.3], seed=1)


def test_paired_pvalue_in_unit_interval():
    a = [0.5, 0.6, 0.4, 0.7, 0.5] * 5
    b = [0.5, 0.55, 0.45, 0.6, 0.5] * 5
    p = paired_bootstrap_pvalue(a, b, seed=2)
    assert 0.0 <= p <= 1.0
