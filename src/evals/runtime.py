"""Runtime/latency aggregation helpers."""

from __future__ import annotations

from collections.abc import Iterable
from statistics import mean

import numpy as np


def summarize_latencies(latencies_ms: Iterable[float]) -> dict[str, float]:
    arr = np.asarray(list(latencies_ms), dtype=float)
    if arr.size == 0:
        return {"avg_latency_ms": 0.0, "p50_latency_ms": 0.0, "p95_latency_ms": 0.0}
    return {
        "avg_latency_ms": float(mean(arr.tolist())),
        "p50_latency_ms": float(np.percentile(arr, 50)),
        "p95_latency_ms": float(np.percentile(arr, 95)),
    }
