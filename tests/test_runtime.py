"""Latency aggregation — shared across every baseline."""

from __future__ import annotations

import pytest

from evals.runtime import summarize_latencies


def test_empty_input_returns_zeros():
    s = summarize_latencies([])
    assert s == {"avg_latency_ms": 0.0, "p50_latency_ms": 0.0, "p95_latency_ms": 0.0}


def test_single_value_all_equal():
    s = summarize_latencies([1234.5])
    assert s["avg_latency_ms"] == pytest.approx(1234.5)
    assert s["p50_latency_ms"] == pytest.approx(1234.5)
    assert s["p95_latency_ms"] == pytest.approx(1234.5)


def test_known_distribution():
    # 1..100 → mean 50.5, median 50.5, p95 95.05
    s = summarize_latencies(list(range(1, 101)))
    assert s["avg_latency_ms"] == pytest.approx(50.5)
    assert s["p50_latency_ms"] == pytest.approx(50.5)
    assert s["p95_latency_ms"] == pytest.approx(95.05)


def test_p95_ge_p50_ge_min():
    s = summarize_latencies([100, 200, 300, 1500, 100, 90, 110])
    assert s["p95_latency_ms"] >= s["p50_latency_ms"]
    assert s["p50_latency_ms"] >= 90


def test_accepts_generator():
    s = summarize_latencies(x * 10 for x in range(1, 11))
    assert s["avg_latency_ms"] == pytest.approx(55.0)
