"""Lightweight timing context manager."""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass
class Elapsed:
    seconds: float = 0.0

    @property
    def ms(self) -> float:
        return self.seconds * 1000.0


@contextmanager
def timed():
    """Measure wall-clock duration of a block.

    Usage:
        with timed() as t:
            ...
        print(t.ms)
    """
    e = Elapsed()
    start = time.perf_counter()
    try:
        yield e
    finally:
        e.seconds = time.perf_counter() - start
