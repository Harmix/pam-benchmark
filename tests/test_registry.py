"""Registry lookups — the only growth surface for adding datasets/baselines."""

from __future__ import annotations

from pathlib import Path

import pytest

from baselines.base import Baseline
from baselines.litellm_baseline import LiteLLMBaseline
from datasets.base import DatasetLoader
from datasets.harmix import loader as harmix_loader
from datasets.harmix.loader import HarmixLoader
from datasets.locomo.loader import LoCoMoLoader
from registry import get_baseline, get_dataset, get_task_runner, known_baselines


def test_get_dataset_locomo_returns_loader():
    loader = get_dataset("locomo")
    assert isinstance(loader, LoCoMoLoader)
    assert isinstance(loader, DatasetLoader)
    assert loader.name == "locomo"
    assert loader.num_samples() > 0


def test_get_dataset_harmix_returns_loader(monkeypatch):
    # Stub the GCS read with the shipped file's bytes so this runs offline.
    shipped = Path(harmix_loader.__file__).parent / "data" / "harmix_bench_cases.json"
    monkeypatch.setattr(harmix_loader, "_read_gcs_bytes", lambda uri: shipped.read_bytes())
    loader = get_dataset("harmix")
    assert isinstance(loader, HarmixLoader)
    assert isinstance(loader, DatasetLoader)
    assert loader.name == "harmix"
    # nazar, nazar_mini, oleksandr, nick.
    assert loader.num_samples() == 4


def test_get_task_runner_harmix_returns_callable():
    runner = get_task_runner("harmix")
    assert callable(runner)


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


def test_known_baselines_includes_pam_mcp():
    assert "pam_mcp" in set(known_baselines())


def test_get_baseline_pam_mcp_builds_harness_composite(tmp_path, monkeypatch):
    monkeypatch.setenv("PAM_API_HOST", "https://staging.api.pam.harmix.ai")
    monkeypatch.setenv("PAM_API_USER", "admin@stub")
    monkeypatch.setenv("PAM_API_PASSWORD", "pw")
    monkeypatch.setenv("PAM_API_KEY", "harmix-key")
    from baselines.pam_mcp.baseline import PamMcpBaseline

    b = get_baseline(
        "pam_mcp",
        harness="claude-code",
        harness_model="vertex-id",
        output_root=tmp_path,
        batch_size=10,
        keep_memory=False,
        max_turns=None,
        debug_user_id=None,
        backup_memory=True,
    )
    assert isinstance(b, PamMcpBaseline)
    assert b.name == "pam_mcp"
    assert b.track == "agentic_memory"
    assert b._mcp_url == "https://staging.api.pam.harmix.ai/v1/mcp/memory"
