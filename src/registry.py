"""Name → object lookups for datasets, tasks, baselines.

Kept deliberately tiny — adding a new dataset/baseline means one line here.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from baselines.base import Baseline
from baselines.litellm_baseline import LiteLLMBaseline
from datasets.base import DatasetLoader
from datasets.locomo.loader import LoCoMoLoader

# Datasets ----------------------------------------------------------------

_DATASETS: dict[str, Callable[..., DatasetLoader]] = {
    "locomo": LoCoMoLoader,
}


def get_dataset(name: str) -> DatasetLoader:
    if name not in _DATASETS:
        raise ValueError(f"unknown dataset: {name!r}. Available: {sorted(_DATASETS)}")
    return _DATASETS[name]()


# Tasks -------------------------------------------------------------------

# `tasks` is a callable that, given (sample, baseline, ...), runs the task.
# Imported lazily to keep startup cheap when only listing options.

def get_task_runner(name: str) -> Callable[..., Any]:
    if name == "locomo":
        from tasks.locomo.pipeline import run_sample
        return run_sample
    raise ValueError(f"unknown task: {name!r}. Available: ['locomo']")


# Baselines ---------------------------------------------------------------

# Baselines accept `model` + arbitrary kwargs. For M1 every named baseline
# routes through LiteLLMBaseline; M2+ subpackages can register their own
# factories here.

_BASELINE_ALIASES = {
    "gpt-4-turbo", "gpt-4-turbo-2024-04-09",
    "gpt-4o", "gpt-4o-mini",
    "gpt-4", "gpt-3.5-turbo",
}


def get_baseline(name: str, *, model: str | None = None, **kwargs: Any) -> Baseline:
    """Resolve a baseline.

    For now any name is interpreted as a LiteLLM model id (or the explicit
    `model=` override wins). Future PAM/Honcho/etc. baselines will branch here.
    """
    chosen_model = model or name
    return LiteLLMBaseline(model=chosen_model, name=name, **kwargs)


def known_baselines() -> list[str]:
    return sorted(_BASELINE_ALIASES)
