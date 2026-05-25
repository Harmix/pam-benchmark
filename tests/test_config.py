"""RunConfig — the single struct that fully describes one benchmark run."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from config import RunConfig


def test_runconfig_minimal_valid():
    cfg = RunConfig(exp_name="x", dataset="locomo", baseline="gpt-4-turbo")
    assert cfg.seed == 42
    assert cfg.judge_model == "gpt-4o"
    assert cfg.resolved_task() == "locomo"
    assert cfg.resolved_output_dir() == Path("outputs") / "x" / "42"


def test_runconfig_task_override():
    cfg = RunConfig(exp_name="x", dataset="locomo", task="custom", baseline="b")
    assert cfg.resolved_task() == "custom"


def test_runconfig_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        RunConfig(exp_name="x", dataset="locomo", baseline="b", unknown_field="boom")


def test_runconfig_baseline_kwargs_must_be_dict():
    with pytest.raises(ValidationError):
        RunConfig(exp_name="x", dataset="locomo", baseline="b", baseline_kwargs="not a dict")
