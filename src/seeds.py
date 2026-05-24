"""Seed every stdlib RNG we touch."""

from __future__ import annotations

import os
import random

import numpy as np


def seed_all(seed: int) -> None:
    """Best-effort deterministic setup.

    Provider-side LLM determinism remains the responsibility of the baseline
    (e.g. `temperature=0` and provider `seed` parameter).
    """
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    np.random.seed(seed)
