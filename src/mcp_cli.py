"""Typer CLI for the MCP-memory-on-harness experiment.

Mirrors `cli.py` but for the harness experiment: it builds the same `RunConfig`
(with `harness` set) and delegates to `runner.run`. Kept separate so the two
experiment types stay legible while sharing all downstream machinery.
"""

from __future__ import annotations

import json
import logging

import typer

from config import RunConfig
from env import load_secrets
from log_setup import configure as configure_logging
from runner import run

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def main(
    exp_name: str = typer.Option(..., "--exp-name", help="Experiment identifier"),
    dataset: str = typer.Option("locomo", "--dataset", help="Dataset name (e.g. locomo)"),
    harness: str = typer.Option("claude-code", "--harness", help="Agentic harness (claude-code)"),
    baseline: str = typer.Option(
        "memory_md_mcp", "--baseline", help="MCP memory baseline (memory_md_mcp | pam_mcp)"
    ),
    harness_model: str = typer.Option(
        None, "--harness-model", help="Base model id for the harness (e.g. a Vertex Claude id)"
    ),
    task: str = typer.Option(None, "--task", help="Task name (defaults to --dataset)"),
    seed: int = typer.Option(42, "--seed", help="Random seed"),
    sample_index: int = typer.Option(
        None, "--sample-index", help="Process only this sample index (default: all)"
    ),
    sample_id: str = typer.Option(
        None,
        "--sample-id",
        help="Process only this sample by string id (e.g. Harmix env 'oleksandr'). "
        "Wins over --sample-index.",
    ),
    max_questions: int = typer.Option(
        None, "--max-questions", help="Cap questions per sample (debug; default: all)"
    ),
    mcp_batch_size: int = typer.Option(
        None,
        "--mcp-batch-size",
        help="Questions per answer batch (default: 1 for harmix, 10 otherwise)",
    ),
    mcp_keep_memory: bool = typer.Option(
        False,
        "--mcp-keep-memory",
        help="Keep each sample's on-disk memory after the run (debug; reused if present). "
        "Default wipes it.",
    ),
    mcp_max_turns: int = typer.Option(
        None, "--mcp-max-turns", help="Cap agent turns per harness invocation"
    ),
    raw_prompt: bool = typer.Option(
        None,
        "--raw-prompt/--no-raw-prompt",
        help="Ask one question at a time, sending the dataset's question verbatim "
        "with no answer-format scaffolding (forces batch size 1). "
        "Default: on for harmix, off otherwise.",
    ),
    judge_model: str = typer.Option(
        None,
        "--judge-model",
        help="LLM-judge model id (default: claude-sonnet-4-5 for harmix, gpt-4o otherwise)",
    ),
    judge_concurrency: int = typer.Option(
        8, "--judge-concurrency", help="Max concurrent judge calls"
    ),
    output_dir: str = typer.Option(
        None, "--output-dir", help="Override outputs/<exp>/<harness>/<seed>"
    ),
    no_mongo: bool = typer.Option(False, "--no-mongo", help="Skip MongoDB writes"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Resolve config and exit"),
    save_responses: bool = typer.Option(
        False, "--save-responses", help="Write Q/A + raw prompts/responses to responses.log"
    ),
    baseline_kwargs: str = typer.Option(
        "{}", "--baseline-kwargs", help="JSON dict of extra baseline kwargs"
    ),
    log_format: str = typer.Option("rich", "--log-format", help="rich | json"),
    pam_debug_user_id: int = typer.Option(
        None,
        "--pam-debug-user-id",
        help="pam_mcp: reuse this Pam user id instead of creating + building a fresh memory",
    ),
    backup_memory: bool = typer.Option(
        False,
        "--backup-memory",
        help=(
            "pam_mcp: keep each conversation's Pam account after the run (no "
            "delete-account) so its memory can be reused later via --pam-debug-user-id."
        ),
    ),
) -> None:
    """Run one (dataset, harness, baseline, seed) MCP-memory experiment end-to-end."""
    load_secrets()
    configure_logging(log_format=log_format, level=logging.INFO)

    try:
        baseline_kwargs_dict = json.loads(baseline_kwargs) if baseline_kwargs else {}
    except json.JSONDecodeError as e:
        raise typer.BadParameter(f"--baseline-kwargs must be valid JSON: {e}") from e

    # Dataset-aware defaults (only applied when the flag was left unset):
    #   - harmix answers one persona-scoped question at a time (batch size 1)
    #     and is graded by claude-sonnet-4-5 with grading notes.
    #   - harmix also skips the numbered-batch answer scaffolding (raw_prompt):
    #     each question is sent verbatim so the agent answers it naturally
    #     instead of being pushed toward a terse "A1: <short answer>" line.
    if raw_prompt is None:
        raw_prompt = dataset == "harmix"
    if mcp_batch_size is None:
        mcp_batch_size = 1 if dataset == "harmix" else 10
    # Raw single-question mode is incompatible with batching — force size 1.
    if raw_prompt:
        mcp_batch_size = 1
    if judge_model is None:
        judge_model = "claude-sonnet-4-5" if dataset == "harmix" else "gpt-4o"

    cfg = RunConfig(
        exp_name=exp_name,
        dataset=dataset,
        baseline=baseline,
        task=task,
        seed=seed,
        sample_index=sample_index,
        sample_id=sample_id,
        max_questions=max_questions,
        baseline_kwargs=baseline_kwargs_dict,
        judge_model=judge_model,
        judge_concurrency=judge_concurrency,
        output_dir=output_dir,
        mongo=not no_mongo,
        dry_run=dry_run,
        save_responses=save_responses,
        log_format=log_format,
        harness=harness,
        harness_model=harness_model,
        mcp_batch_size=mcp_batch_size,
        mcp_keep_memory=mcp_keep_memory,
        mcp_max_turns=mcp_max_turns,
        raw_prompt=raw_prompt,
        pam_debug_user_id=pam_debug_user_id,
        backup_memory=backup_memory,
    )
    run(cfg)


if __name__ == "__main__":
    app()
