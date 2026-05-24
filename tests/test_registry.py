"""Registry lookups — the only growth surface for adding datasets/baselines."""

from __future__ import annotations

import pytest

from baselines.base import Baseline
from baselines.litellm_baseline import LiteLLMBaseline
from datasets.base import DatasetLoader
from datasets.locomo.loader import LoCoMoLoader
from registry import get_baseline, get_dataset, get_task_runner, known_baselines


def test_get_dataset_locomo_returns_loader():
    loader = get_dataset("locomo")
    assert isinstance(loader, LoCoMoLoader)
    assert isinstance(loader, DatasetLoader)
    assert loader.name == "locomo"
    assert loader.num_samples() > 0


def test_get_dataset_unknown_raises_with_available_list():
    with pytest.raises(ValueError, match="unknown dataset"):
        get_dataset("nope")


def test_get_task_runner_locomo_returns_callable():
    runner = get_task_runner("locomo")
    assert callable(runner)


def test_get_task_runner_unknown_raises():
    with pytest.raises(ValueError, match="unknown task"):
        get_task_runner("nope")


def test_get_baseline_returns_litellm_for_any_name():
    b = get_baseline("gpt-4-turbo")
    assert isinstance(b, LiteLLMBaseline)
    assert isinstance(b, Baseline)
    assert b.name == "gpt-4-turbo"
    assert b.model == "gpt-4-turbo"
    assert b.track == "out_of_the_box"


def test_get_baseline_with_model_override():
    b = get_baseline("my-experimental-config", model="gpt-4o", temperature=0.1)
    assert b.name == "my-experimental-config"
    assert b.model == "gpt-4o"
    assert b.temperature == pytest.approx(0.1)


def test_known_baselines_includes_m1_targets():
    known = set(known_baselines())
    assert "gpt-4-turbo" in known
    assert "gpt-4o" in known
