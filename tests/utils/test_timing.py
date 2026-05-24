"""`timed()` context manager — wall-clock helper used in baselines + judge."""

from __future__ import annotations

import time

from utils.timing import timed


def test_timed_records_seconds():
    with timed() as t:
        time.sleep(0.01)
    assert t.seconds >= 0.01
    assert t.ms >= 10.0
