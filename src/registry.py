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
    "pam",
    "memory_md_mcp",
    "gpt-4-turbo",
    "gpt-4-turbo-2024-04-09",
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4",
    "gpt-3.5-turbo",
}

# MCP memory baselines (run on top of an agentic harness).
_MCP_BACKENDS = {"memory_md_mcp"}


def get_baseline(name: str, *, model: str | None = None, **kwargs: Any) -> Baseline:
    """Resolve a baseline.

    `name == "pam"` returns the in-house Pam memory baseline. MCP memory
    baselines (e.g. `memory_md_mcp`) compose a harness + a memory backend.
    Everything else is a LiteLLM model id (or the explicit `model=` override).
    """
    if name == "pam":
        from baselines.pam.baseline import PamBaseline

        return PamBaseline(**kwargs)

    if name in _MCP_BACKENDS:
        return _build_mcp_baseline(name, **kwargs)

    chosen_model = model or name
    return LiteLLMBaseline(model=chosen_model, name=name, **kwargs)


def _build_mcp_baseline(name: str, **kwargs: Any) -> Baseline:
    """Compose `McpHarnessBaseline(harness, backend)` from kwargs supplied by the
    runner (`harness`, `harness_model`, `output_root`, batch/turn/debug knobs)."""
    from baselines.mcp.base import McpHarnessBaseline
    from baselines.mcp.memory_md.backend import MemoryMdBackend

    harness_name = kwargs.pop("harness", None) or "claude-code"
    harness_model = kwargs.pop("harness_model", None)
    harness = get_harness(harness_name, model=harness_model, max_turns=kwargs.get("max_turns"))

    backends = {"memory_md_mcp": MemoryMdBackend}
    backend = backends[name]()
    return McpHarnessBaseline(
        harness=harness, backend=backend, harness_model=harness_model, **kwargs
    )


def get_harness(name: str, *, model: str | None = None, **kwargs: Any) -> Any:
    """Resolve an agentic harness by name."""
    if name == "claude-code":
        from harnesses.claude_code.harness import ClaudeCodeHarness

        return ClaudeCodeHarness(model=model, max_turns=kwargs.get("max_turns"))
    raise ValueError(f"unknown harness: {name!r}. Available: ['claude-code']")


def known_baselines() -> list[str]:
    return sorted(_BASELINE_ALIASES)
