"""Runner — orchestrates one RunConfig end-to-end.

Loads dataset, runs task with baseline, scores with F1 + LLM judge, writes
per-sample document to MongoDB. The `qa_responses` nested array carries the
full per-question payload (predictions, judge verdicts, tokens, latency).
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.console import Console

from config import RunConfig
from datasets.locomo.schemas import CATEGORY_NAMES, LoCoMoSample
from evals.llm_judge import judge_many
from evals.qa_f1 import score_locomo_qa
from evals.runtime import summarize_latencies
from mongo import write_sample_result
from progress import add_sample_task, progress_for
from registry import get_baseline, get_dataset, get_task_runner
from seeds import seed_all
from tasks.locomo.pipeline import LoCoMoPrediction
from utils.io import write_json

logger = logging.getLogger(__name__)


@dataclass
class SampleResult:
    sample_id: str
    sample_index: int
    document: dict[str, Any]


def _provenance() -> dict[str, str]:
    """Best-effort git + image provenance for Mongo docs."""
    info: dict[str, str] = {}
    try:
        info["git_commit"] = (
            subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL)
            .decode()
            .strip()
        )
    except Exception:
        info["git_commit"] = ""
    info["image_digest"] = (subprocess.os.environ.get("IMAGE_DIGEST") or "").strip()
    try:
        lock = Path(__file__).resolve().parent.parent / "uv.lock"
        if lock.exists():
            from utils.io import sha256  # local import to avoid circulars

            info["uv_lock_hash"] = sha256(lock)
    except Exception:
        info["uv_lock_hash"] = ""
    return info


def _aggregate(
    predictions: list[LoCoMoPrediction],
    f1_scores: list[float],
    judge_results: list[Any],
) -> dict[str, Any]:
    """Build the aggregate (non-qa_responses) portion of the Mongo document."""
    total = len(predictions)
    correct_f1 = sum(1 for s in f1_scores if s >= 0.5)
    judge_correct = sum(1 for j in judge_results if j.correct)

    # Per-category aggregates
    cat_f1: dict[int, list[float]] = {}
    cat_judge: dict[int, list[float]] = {}
    cat_judge_correct: dict[int, int] = {}
    for pred, f1, j in zip(predictions, f1_scores, judge_results, strict=True):
        cat_f1.setdefault(pred.category, []).append(f1)
        cat_judge.setdefault(pred.category, []).append(j.score)
        cat_judge_correct.setdefault(pred.category, 0)
        if j.correct:
            cat_judge_correct[pred.category] += 1

    per_cat: dict[str, Any] = {}
    for cat, scores in cat_f1.items():
        name = CATEGORY_NAMES.get(cat, f"category_{cat}")
        per_cat[f"category_{name}_accuracy"] = round(sum(scores) / len(scores), 4)
        per_cat[f"category_{name}_count"] = len(scores)
        judge_scores = cat_judge[cat]
        per_cat[f"category_{name}_llm_judge_accuracy"] = round(
            cat_judge_correct[cat] / len(judge_scores), 4
        )
        per_cat[f"category_{name}_llm_judge_total"] = len(judge_scores)

    latencies = summarize_latencies(p.latency_ms for p in predictions)
    total_in_tok = sum(p.input_tokens for p in predictions)
    total_out_tok = sum(p.output_tokens for p in predictions)
    total_cost = sum(p.est_cost_usd for p in predictions)

    overall_f1 = sum(f1_scores) / total if total else 0.0
    judge_acc = judge_correct / total if total else 0.0

    return {
        "total_questions": total,
        "correct_count": correct_f1,
        "incorrect_count": total - correct_f1,
        "overall_accuracy": round(overall_f1, 4),
        "total_f1_sum": round(sum(f1_scores), 4),
        "judge_accuracy": round(judge_acc, 4),
        "judge_correct_count": judge_correct,
        "total_input_tokens": total_in_tok,
        "total_output_tokens": total_out_tok,
        "total_cost_usd": round(total_cost, 6),
        **latencies,
        **per_cat,
    }


def _qa_responses(
    predictions: list[LoCoMoPrediction],
    f1_scores: list[float],
    judge_results: list[Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pred, f1, j in zip(predictions, f1_scores, judge_results, strict=True):
        rows.append(
            {
                "question_num": pred.question_num,
                "question": pred.question,
                "expected_answer": pred.expected_answer,
                "model_answer": pred.model_answer,
                "category": pred.category,
                "category_name": pred.category_name,
                "evidence": pred.evidence,
                "is_adversarial": pred.is_adversarial,
                "f1_score": round(f1, 4),
                "judge_correct": j.correct,
                "judge_score": round(j.score, 4),
                "judge_confidence": round(j.confidence, 4),
                "judge_reasoning": j.reasoning,
                "input_tokens": pred.input_tokens,
                "output_tokens": pred.output_tokens,
                "est_cost_usd": round(pred.est_cost_usd, 6),
                "latency_ms": round(pred.latency_ms, 2),
            }
        )
    return rows


async def _process_sample(
    sample: LoCoMoSample,
    sample_index: int,
    cfg: RunConfig,
    baseline: Any,
    task_runner: Any,
    progress: Any,
) -> SampleResult:
    n_questions = (
        len(sample.qa) if cfg.max_questions is None else min(cfg.max_questions, len(sample.qa))
    )
    task_id = add_sample_task(progress, sample.sample_id, n_questions)

    def _advance(_pred: LoCoMoPrediction) -> None:
        progress.advance(task_id, 1)

    start = time.perf_counter()
    predictions: list[LoCoMoPrediction] = await task_runner(
        sample,
        baseline=baseline,
        seed=cfg.seed,
        model_name=cfg.baseline_model or cfg.baseline,
        max_questions=cfg.max_questions,
        on_question_done=_advance,
    )
    answer_seconds = time.perf_counter() - start

    # F1 (sync; local)
    f1_scores = [
        score_locomo_qa(
            prediction=p.model_answer,
            ground_truth=p.expected_answer,
            category=p.category,
        )
        for p in predictions
    ]

    # LLM judge (async; concurrency-capped)
    triples = [(p.question, p.expected_answer, p.model_answer) for p in predictions]
    judge_start = time.perf_counter()
    judge_results = await judge_many(
        triples,
        judge_model=cfg.judge_model,
        concurrency=cfg.judge_concurrency,
    )
    judge_seconds = time.perf_counter() - judge_start

    aggregate = _aggregate(predictions, f1_scores, judge_results)
    qa_rows = _qa_responses(predictions, f1_scores, judge_results)

    baseline_extras: dict[str, Any] = {}
    if hasattr(baseline, "extras"):
        try:
            baseline_extras = baseline.extras() or {}
        except Exception:  # pragma: no cover — defensive; baselines shouldn't raise here
            baseline_extras = {}

    document: dict[str, Any] = {
        "exp_name": cfg.exp_name,
        "sample_id": sample.sample_id,
        "sample_index": sample_index,
        "seed": cfg.seed,
        "baseline": cfg.baseline,
        "baseline_kwargs": cfg.baseline_kwargs,
        "judge_model": cfg.judge_model,
        "dataset_name": f"{cfg.dataset}@1.0",
        "task_name": cfg.resolved_task(),
        **aggregate,
        **baseline_extras,
        "qa_responses": qa_rows,
        "execution_time_seconds": round(answer_seconds + judge_seconds, 2),
        "answer_phase_seconds": round(answer_seconds, 2),
        "judge_phase_seconds": round(judge_seconds, 2),
        "max_questions": cfg.max_questions or 0,
        **_provenance(),
    }

    return SampleResult(sample_id=sample.sample_id, sample_index=sample_index, document=document)


async def _run_async(cfg: RunConfig, console: Console) -> dict[str, Any]:
    seed_all(cfg.seed)
    loader = get_dataset(cfg.dataset)
    task_runner = get_task_runner(cfg.resolved_task())
    baseline_extra: dict[str, Any] = {}
    if cfg.baseline == "pam":
        baseline_extra = {
            "batch_size": cfg.pam_batch_size,
            "debug_user_id": cfg.pam_debug_user_id,
        }
    baseline = get_baseline(
        cfg.baseline,
        model=cfg.baseline_model,
        **{**cfg.baseline_kwargs, **baseline_extra},
    )
    await baseline.setup(seed=cfg.seed)

    # Decide which samples to process
    if cfg.sample_index is not None:
        indices = [cfg.sample_index]
    else:
        indices = list(range(loader.num_samples()))

    console.log(
        f"Starting run: dataset={cfg.dataset} baseline={cfg.baseline} "
        f"exp_name={cfg.exp_name} seed={cfg.seed} samples={indices} "
        f"max_questions={cfg.max_questions or 'all'} judge={cfg.judge_model}"
    )

    out_dir = cfg.resolved_output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "config.yaml", cfg.model_dump())

    results: list[SampleResult] = []
    with progress_for(console=console) as progress:
        for sample_index in indices:
            sample = loader.get_sample(sample_index)
            if cfg.dry_run:
                console.log(f"[yellow]dry-run[/yellow] would process {sample.sample_id}")
                continue
            r = await _process_sample(sample, sample_index, cfg, baseline, task_runner, progress)
            results.append(r)
            if cfg.mongo:
                write_sample_result(dataset=cfg.dataset, document=r.document)

    await baseline.teardown()

    # Aggregate across samples for the local metrics.json
    overall = {
        "exp_name": cfg.exp_name,
        "seed": cfg.seed,
        "baseline": cfg.baseline,
        "dataset": cfg.dataset,
        "samples": [
            {
                "sample_id": r.sample_id,
                "sample_index": r.sample_index,
                "total_questions": r.document.get("total_questions"),
                "overall_accuracy": r.document.get("overall_accuracy"),
                "judge_accuracy": r.document.get("judge_accuracy"),
                "total_input_tokens": r.document.get("total_input_tokens"),
                "total_output_tokens": r.document.get("total_output_tokens"),
                "total_cost_usd": r.document.get("total_cost_usd"),
                "avg_latency_ms": r.document.get("avg_latency_ms"),
                "execution_time_seconds": r.document.get("execution_time_seconds"),
            }
            for r in results
        ],
    }
    write_json(out_dir / "metrics.json", overall)
    console.log(f"[green]Run complete.[/green] metrics → {out_dir / 'metrics.json'}")
    return overall


def run(cfg: RunConfig) -> dict[str, Any]:
    """Sync entry point — used by the CLI and any future programmatic caller."""
    console = Console()
    return asyncio.run(_run_async(cfg, console))
