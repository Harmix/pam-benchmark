"""Typer CLI for `scripts/run_benchmark.py`.

The CLI is intentionally thin — it parses flags, builds a `RunConfig`, and
delegates everything else to `runner.run`. Adding a flag = adding one line
in `RunConfig` + one option below.
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
    dataset: str = typer.Option(..., "--dataset", help="Dataset name (e.g. locomo)"),
    baseline: str = typer.Option(..., "--baseline", help="Baseline name (e.g. gpt-4-turbo)"),
    exp_name: str = typer.Option(..., "--exp-name", help="Experiment identifier"),
    task: str = typer.Option(None, "--task", help="Task name (defaults to --dataset)"),
    seed: int = typer.Option(42, "--seed", help="Random seed"),
    sample_index: int = typer.Option(
        None, "--sample-index", help="Process only this sample index (default: all)"
    ),
    max_questions: int = typer.Option(
        None, "--max-questions", help="Cap questions per sample (default: all)"
    ),
    baseline_model: str = typer.Option(None, "--baseline-model", help="Override baseline model id"),
    baseline_kwargs: str = typer.Option(
        "{}", "--baseline-kwargs", help="JSON dict of extra baseline kwargs"
    ),
    judge_model: str = typer.Option("gpt-4o", "--judge-model", help="LLM-judge model id"),
    judge_concurrency: int = typer.Option(
        8, "--judge-concurrency", help="Max concurrent judge calls"
    ),
    output_dir: str = typer.Option(None, "--output-dir", help="Override outputs/<exp>/<seed>"),
    no_mongo: bool = typer.Option(False, "--no-mongo", help="Skip MongoDB writes"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Resolve config and exit"),
    save_responses: bool = typer.Option(
        False,
        "--save-responses",
        help=(
            "Write every question + expected answer + baseline answer to "
            "responses.log in the output dir (debugging aid)."
        ),
    ),
    log_format: str = typer.Option(
        "rich", "--log-format", help="rich | json (json for Cloud Logging)"
    ),
    pam_batch_size: int = typer.Option(
        10, "--pam-batch-size", help="Pam: questions per SSE batch (ignored by other baselines)"
    ),
    pam_debug_user_id: int = typer.Option(
        None,
        "--pam-debug-user-id",
        help="Pam: reuse this user id instead of creating + uploading + building a fresh memory",
    ),
    backup_memory: bool = typer.Option(
        False,
        "--backup-memory",
        help=(
            "Pam: keep each conversation's user account after the run instead of "
            "deleting it (no delete-account call). The account and its built "
            "memory are preserved so they can be reused later via "
            "--pam-debug-user-id."
        ),
    ),
) -> None:
    """Run one (dataset, baseline, seed) end-to-end."""
    load_secrets()
    configure_logging(log_format=log_format, level=logging.INFO)

    try:
        baseline_kwargs_dict = json.loads(baseline_kwargs) if baseline_kwargs else {}
    except json.JSONDecodeError as e:
        raise typer.BadParameter(f"--baseline-kwargs must be valid JSON: {e}") from e

    cfg = RunConfig(
        dataset=dataset,
        baseline=baseline,
        exp_name=exp_name,
        task=task,
        seed=seed,
        sample_index=sample_index,
        max_questions=max_questions,
        baseline_model=baseline_model,
        baseline_kwargs=baseline_kwargs_dict,
        judge_model=judge_model,
        judge_concurrency=judge_concurrency,
        output_dir=output_dir,
        mongo=not no_mongo,
        dry_run=dry_run,
        save_responses=save_responses,
        log_format=log_format,
        pam_batch_size=pam_batch_size,
        pam_debug_user_id=pam_debug_user_id,
        backup_memory=backup_memory,
    )
    run(cfg)


if __name__ == "__main__":
    app()
