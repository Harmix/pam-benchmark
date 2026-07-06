"""RunConfig — the single struct that fully describes one benchmark run."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RunConfig(BaseModel):
    """One invocation of `scripts/run_benchmark.py`.

    A single `(exp_name, dataset, baseline, seed)` tuple is the unit of work.
    Multi-seed runs = multiple invocations with the same `exp_name` and
    different `seed` values.
    """

    model_config = ConfigDict(extra="forbid")

    # Identity
    exp_name: str
    dataset: str
    task: str | None = None  # defaults to `dataset` at resolve time
    baseline: str
    seed: int = 42

    # Baseline configuration
    baseline_model: str | None = None  # overrides registry default
    baseline_kwargs: dict[str, Any] = Field(default_factory=dict)

    # Judge
    judge_model: str = "gpt-4o"
    judge_concurrency: int = 8

    # Scope
    sample_index: int | None = None  # None = all
    # Select a single sample by its string id (e.g. a Harmix environment id like
    # "oleksandr"). Resolved to an index at run time; wins over sample_index.
    sample_id: str | None = None
    max_questions: int | None = None  # None = all per sample

    # Outputs
    output_dir: Path | None = None  # defaults to ./outputs/<exp>/<seed>
    log_format: str = "rich"  # "rich" | "json"
    mongo: bool = True
    dry_run: bool = False
    # When True, dump every question + expected answer + baseline answer to a
    # human-readable `responses.log` in the output dir. Debug aid only.
    save_responses: bool = False

    # MCP-on-harness experiment (None ⇒ classic API/LiteLLM/Pam run)
    harness: str | None = None  # e.g. "claude-code"
    harness_model: str | None = None  # base model id for the harness
    mcp_batch_size: int = 10  # questions per batch (mirrors pam_batch_size)
    mcp_keep_memory: bool = False  # keep per-sample memory (debug); default wipes
    mcp_max_turns: int | None = None  # cap agent turns per harness invocation

    # Pam-specific (ignored by other baselines)
    pam_batch_size: int = 10
    pam_debug_user_id: int | None = None
    # When True the per-conversation Pam account is NOT deleted after the run;
    # the account and its built memory are kept so they can be reused later via
    # pam_debug_user_id.
    backup_memory: bool = False

    def resolved_task(self) -> str:
        return self.task or self.dataset

    def resolved_output_dir(self) -> Path:
        if self.output_dir:
            return self.output_dir
        base = Path("outputs") / self.exp_name
        # Harness runs insert <harness> so multiple harnesses under one
        # experiment don't collide: outputs/<exp>/<harness>/<seed>/.
        if self.harness:
            base = base / self.harness
        return base / str(self.seed)
