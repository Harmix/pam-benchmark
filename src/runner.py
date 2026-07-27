"""Runner — orchestrates one RunConfig end-to-end.

Loads dataset, runs task with baseline, scores with F1 + LLM judge, writes
per-sample document to MongoDB. The `qa_responses` nested array carries the
full per-question payload (predictions, judge verdicts, tokens, latency).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.console import Console

from config import RunConfig
from datasets.locomo.schemas import CATEGORY_NAMES, LoCoMoSample
from evals.llm_judge import judge_many, judge_many_with_notes
from evals.qa_f1 import score_locomo_qa
from evals.runtime import summarize_latencies
from mongo import write_sample_result
from progress import add_sample_task, progress_for
from registry import get_baseline, get_dataset, get_task_runner
from seeds import seed_all
from tasks.harmix.pipeline import HarmixPrediction
from tasks.locomo.pipeline import LoCoMoPrediction
from utils.io import write_json

logger = logging.getLogger(__name__)


@dataclass
class SampleResult:
    sample_id: str
    sample_index: int
    document: dict[str, Any]


def _provenance() -> dict[str, str]:
    """Best-effort dependency provenance for Mongo docs."""
    info: dict[str, str] = {}
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
    total_prompt_tok = sum(p.prompt_tokens for p in predictions)
    total_context_tok = sum(p.context_tokens for p in predictions)
    total_agent_in_tok = sum(p.agent_input_tokens for p in predictions)
    total_agent_out_tok = sum(p.agent_output_tokens for p in predictions)
    total_agent_cache_read_tok = sum(p.agent_cache_read_tokens for p in predictions)
    total_agent_cache_write_tok = sum(p.agent_cache_write_tokens for p in predictions)
    # enriched_user_prompt_tokens is None for baselines where it doesn't apply
    # (e.g. claude-code) → keep the total None rather than coercing to 0.
    _enriched = [p.enriched_user_prompt_tokens for p in predictions]
    total_enriched_prompt_tok = (
        None if _enriched and all(v is None for v in _enriched) else sum(v or 0 for v in _enriched)
    )
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
        "total_prompt_tokens": total_prompt_tok,
        "total_context_tokens": total_context_tok,
        "total_agent_input_tokens": total_agent_in_tok,
        "total_agent_output_tokens": total_agent_out_tok,
        "total_agent_cache_read_tokens": total_agent_cache_read_tok,
        "total_agent_cache_write_tokens": total_agent_cache_write_tok,
        "total_enriched_user_prompt_tokens": total_enriched_prompt_tok,
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
                "prompt_tokens": pred.prompt_tokens,
                "context_tokens": pred.context_tokens,
                "agent_input_tokens": pred.agent_input_tokens,
                "agent_output_tokens": pred.agent_output_tokens,
                "agent_cache_read_tokens": pred.agent_cache_read_tokens,
                "agent_cache_write_tokens": pred.agent_cache_write_tokens,
                "enriched_user_prompt_tokens": pred.enriched_user_prompt_tokens,
                "est_cost_usd": round(pred.est_cost_usd, 6),
                "latency_ms": round(pred.latency_ms, 2),
            }
        )
    return rows


def _append_log(path: Path, text: str) -> None:
    """Append `text` and flush — opened per call so the log is readable mid-run."""
    with path.open("a", encoding="utf-8") as fh:
        fh.write(text)


def _responses_log_header(sample_id: str, sample_index: int) -> str:
    return "\n".join(["=" * 78, f"Sample: {sample_id} (index {sample_index})", "=" * 78, "", ""])


def _responses_log_entry(preds: list[LoCoMoPrediction]) -> str:
    """One batch's raw prompt + raw model response, written as soon as the model
    answers (before judging — no f1/judge fields here). A batch shares one model
    exchange, so the prompt/response are printed once and the per-question
    expected/parsed answers are listed below them."""
    if not preds:
        return ""
    nums = [p.question_num for p in preds]
    span = f"Q{nums[0]}" if len(nums) == 1 else f"Q{nums[0]}-Q{nums[-1]}"
    expected = "\n".join(f"Q{p.question_num}: {p.expected_answer}" for p in preds)
    parsed = "\n".join(f"A{p.question_num}: {p.model_answer}" for p in preds)
    return (
        "\n".join(
            [
                f"[Batch {span}]",
                "--- RAW PROMPT ---",
                preds[0].raw_prompt,
                "--- RAW MODEL RESPONSE ---",
                preds[0].raw_response_text,
                "--- EXPECTED ---",
                expected,
                "--- PARSED ANSWER ---",
                parsed,
                "",
            ]
        )
        + "\n"
    )


async def _process_sample(
    sample: LoCoMoSample,
    sample_index: int,
    cfg: RunConfig,
    baseline: Any,
    task_runner: Any,
    progress: Any,
    responses_log: Path | None = None,
) -> SampleResult:
    n_questions = (
        len(sample.qa) if cfg.max_questions is None else min(cfg.max_questions, len(sample.qa))
    )
    task_id = add_sample_task(progress, sample.sample_id, n_questions)

    if responses_log is not None:
        _append_log(responses_log, _responses_log_header(sample.sample_id, sample_index))

    def _advance(_pred: LoCoMoPrediction) -> None:
        progress.advance(task_id, 1)

    def _log_batch(preds: list[LoCoMoPrediction]) -> None:
        # Flush each batch to disk immediately so the log can be tailed live.
        if responses_log is not None:
            _append_log(responses_log, _responses_log_entry(preds))

    start = time.perf_counter()
    predictions: list[LoCoMoPrediction] = await task_runner(
        sample,
        baseline=baseline,
        seed=cfg.seed,
        model_name=cfg.baseline_model or cfg.baseline,
        max_questions=cfg.max_questions,
        on_question_done=_advance,
        on_batch_done=_log_batch,
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

    # Baseline-supplied additions to baseline_kwargs (e.g. Pam's agent_model_used
    # read from message_metrics).
    baseline_kwargs = dict(cfg.baseline_kwargs)
    if hasattr(baseline, "baseline_kwargs_extra"):
        with contextlib.suppress(Exception):  # defensive — baselines shouldn't raise here
            baseline_kwargs.update(baseline.baseline_kwargs_extra() or {})

    document: dict[str, Any] = {
        "exp_name": cfg.exp_name,
        "sample_id": sample.sample_id,
        "sample_index": sample_index,
        "seed": cfg.seed,
        "baseline": cfg.baseline,
        "baseline_kwargs": baseline_kwargs,
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


@dataclass
class _HarmixVerdict:
    """Aggregated judge verdict for one question (avg@k when n_samples>1).

    For K=1 this is just the single verdict (frac_correct ∈ {0,1}, std 0). For K>1
    it holds the avg@k stats plus the representative sample we display.
    """

    correct: bool  # representative sample's correctness (drives the display bucket)
    score: float  # representative sample's score
    confidence: float
    reasoning: str
    mean_score: float  # mean of the K judge scores
    frac_correct: float  # mean of the K correct flags == avg@k for this question
    score_std: float  # std of the K judge scores
    n_samples: int
    shown_answer: str  # the sample answer closest to the mean score (what we show)


def _aggregate_samples(answers: list[str], verdicts: list[Any]) -> _HarmixVerdict:
    """Average K per-sample verdicts and pick the closest-to-mean representative."""
    scores = [float(v.score) for v in verdicts]
    corrects = [1.0 if v.correct else 0.0 for v in verdicts]
    mean_score = statistics.fmean(scores) if scores else 0.0
    frac = statistics.fmean(corrects) if corrects else 0.0
    std = statistics.pstdev(scores) if len(scores) > 1 else 0.0
    # Representative = the sample whose score is closest to the mean; ties → the
    # one the judge was most confident about. Keeps the shown answer consistent
    # with the reported per-question number (not the best/worst draw).
    rep = min(
        range(len(verdicts)),
        key=lambda j: (abs(scores[j] - mean_score), -float(verdicts[j].confidence)),
    )
    rv = verdicts[rep]
    shown = answers[rep] if rep < len(answers) else (answers[0] if answers else "")
    return _HarmixVerdict(
        correct=bool(rv.correct),
        score=float(rv.score),
        confidence=float(rv.confidence),
        reasoning=rv.reasoning,
        mean_score=mean_score,
        frac_correct=frac,
        score_std=std,
        n_samples=len(verdicts),
        shown_answer=shown,
    )


def _aggregate_harmix(
    predictions: list[HarmixPrediction],
    verdict_by_index: dict[int, Any],
) -> dict[str, Any]:
    """Aggregate for Harmix: LLM-judge only (no F1, no categories).

    Headline metric is **avg@k** — the mean over judged questions of each
    question's fraction-correct across its K samples (= plain accuracy when K=1).
    Cases with `expected_answer is None` (open/draft tasks) are answered and
    recorded but excluded — `judged_count` is the denominator.
    """
    total = len(predictions)
    judged = len(verdict_by_index)
    fracs = [v.frac_correct for v in verdict_by_index.values()]
    # Expected #correct across avg@k (float; equals an integer count when K=1).
    judge_correct = sum(fracs)
    judge_acc_std = statistics.pstdev(fracs) if len(fracs) > 1 else 0.0
    n_samples = max((v.n_samples for v in verdict_by_index.values()), default=1)

    latencies = summarize_latencies(p.latency_ms for p in predictions)
    total_in_tok = sum(p.input_tokens for p in predictions)
    total_out_tok = sum(p.output_tokens for p in predictions)
    total_prompt_tok = sum(p.prompt_tokens for p in predictions)
    total_context_tok = sum(p.context_tokens for p in predictions)
    total_agent_in_tok = sum(p.agent_input_tokens for p in predictions)
    total_agent_out_tok = sum(p.agent_output_tokens for p in predictions)
    total_agent_cache_read_tok = sum(p.agent_cache_read_tokens for p in predictions)
    total_agent_cache_write_tok = sum(p.agent_cache_write_tokens for p in predictions)
    total_cost = sum(p.est_cost_usd for p in predictions)

    judge_acc = judge_correct / judged if judged else 0.0

    return {
        "total_questions": total,
        "judged_count": judged,
        "unjudged_count": total - judged,  # open tasks with no gold answer
        "judge_accuracy": round(judge_acc, 4),  # avg@k (== accuracy when K=1)
        "judge_accuracy_std": round(judge_acc_std, 4),  # std across questions of frac-correct
        "samples_per_question": n_samples,
        "judge_correct_count": round(judge_correct, 4),  # expected #correct (float for K>1)
        "total_input_tokens": total_in_tok,
        "total_output_tokens": total_out_tok,
        "total_prompt_tokens": total_prompt_tok,
        "total_context_tokens": total_context_tok,
        "total_agent_input_tokens": total_agent_in_tok,
        "total_agent_output_tokens": total_agent_out_tok,
        "total_agent_cache_read_tokens": total_agent_cache_read_tok,
        "total_agent_cache_write_tokens": total_agent_cache_write_tok,
        "total_cost_usd": round(total_cost, 6),
        **latencies,
    }


def _qa_responses_harmix(
    predictions: list[HarmixPrediction],
    verdict_by_index: dict[int, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i, pred in enumerate(predictions):
        v = verdict_by_index.get(i)
        rows.append(
            {
                "question_num": pred.question_num,
                "case_id": pred.case_id,
                "question": pred.question,
                "expected_answer": pred.expected_answer,
                "model_answer": pred.model_answer,
                "grading_notes": pred.grading_notes,
                "judged": v is not None,
                "judge_correct": v.correct if v is not None else None,
                "judge_score": round(v.score, 4) if v is not None else None,
                "judge_confidence": round(v.confidence, 4) if v is not None else None,
                "judge_reasoning": v.reasoning if v is not None else None,
                # avg@k: shown model_answer above is the closest-to-mean sample; the
                # K individual answers are NOT stored — only these summary stats.
                "n_samples": v.n_samples if v is not None else pred.n_samples,
                "mean_score": round(v.mean_score, 4) if v is not None else None,
                "score_std": round(v.score_std, 4) if v is not None else None,
                "frac_correct": round(v.frac_correct, 4) if v is not None else None,
                "input_tokens": pred.input_tokens,
                "output_tokens": pred.output_tokens,
                "prompt_tokens": pred.prompt_tokens,
                "context_tokens": pred.context_tokens,
                "agent_input_tokens": pred.agent_input_tokens,
                "agent_output_tokens": pred.agent_output_tokens,
                "agent_cache_read_tokens": pred.agent_cache_read_tokens,
                "agent_cache_write_tokens": pred.agent_cache_write_tokens,
                "est_cost_usd": round(pred.est_cost_usd, 6),
                "latency_ms": round(pred.latency_ms, 2),
            }
        )
    return rows


async def _process_sample_harmix(
    sample: Any,
    sample_index: int,
    cfg: RunConfig,
    baseline: Any,
    task_runner: Any,
    progress: Any,
    responses_log: Path | None = None,
) -> SampleResult:
    """Process one Harmix environment: answer its cases, judge with grading notes."""
    n_questions = (
        len(sample.qa) if cfg.max_questions is None else min(cfg.max_questions, len(sample.qa))
    )
    task_id = add_sample_task(progress, sample.sample_id, n_questions)

    if responses_log is not None:
        _append_log(responses_log, _responses_log_header(sample.sample_id, sample_index))

    def _advance(_pred: HarmixPrediction) -> None:
        progress.advance(task_id, 1)

    def _log_batch(preds: list[HarmixPrediction]) -> None:
        if responses_log is not None:
            _append_log(responses_log, _responses_log_entry(preds))

    start = time.perf_counter()
    predictions: list[HarmixPrediction] = await task_runner(
        sample,
        baseline=baseline,
        seed=cfg.seed,
        model_name=cfg.baseline_model or cfg.baseline,
        max_questions=cfg.max_questions,
        on_question_done=_advance,
        on_batch_done=_log_batch,
    )
    answer_seconds = time.perf_counter() - start

    # LLM judge (sonnet-4-5 by default) — only cases with a gold answer. avg@k:
    # judge EACH of a question's K samples (flattened for one concurrent pass),
    # then average and pick the representative. K=1 reduces to one item per case.
    judgeable = [(i, p) for i, p in enumerate(predictions) if p.expected_answer is not None]
    flat_items: list[tuple[str, str, str, str | None]] = []
    flat_map: list[tuple[int, int]] = []  # (prediction index, sample index)
    for i, p in judgeable:
        answers = p.sample_answers or [p.model_answer]
        for s_idx, ans in enumerate(answers):
            flat_items.append((p.question, p.expected_answer or "", ans, p.grading_notes))
            flat_map.append((i, s_idx))
    judge_start = time.perf_counter()
    flat_verdicts = await judge_many_with_notes(
        flat_items, judge_model=cfg.judge_model, concurrency=cfg.judge_concurrency
    )
    judge_seconds = time.perf_counter() - judge_start
    # Group verdicts back per question, average, and record the representative.
    grouped: dict[int, list[tuple[int, Any]]] = {}
    for (i, s_idx), v in zip(flat_map, flat_verdicts, strict=True):
        grouped.setdefault(i, []).append((s_idx, v))
    verdict_by_index: dict[int, _HarmixVerdict] = {}
    for i, sv in grouped.items():
        sv.sort(key=lambda x: x[0])
        verdicts = [v for _, v in sv]
        answers = predictions[i].sample_answers or [predictions[i].model_answer]
        agg = _aggregate_samples(answers, verdicts)
        verdict_by_index[i] = agg
        # Display the representative (closest-to-mean) answer in the report.
        predictions[i].model_answer = agg.shown_answer

    aggregate = _aggregate_harmix(predictions, verdict_by_index)
    qa_rows = _qa_responses_harmix(predictions, verdict_by_index)

    baseline_extras: dict[str, Any] = {}
    if hasattr(baseline, "extras"):
        try:
            baseline_extras = baseline.extras() or {}
        except Exception:  # pragma: no cover — defensive
            baseline_extras = {}

    baseline_kwargs = dict(cfg.baseline_kwargs)
    if hasattr(baseline, "baseline_kwargs_extra"):
        with contextlib.suppress(Exception):  # defensive
            baseline_kwargs.update(baseline.baseline_kwargs_extra() or {})

    document: dict[str, Any] = {
        "exp_name": cfg.exp_name,
        "sample_id": sample.sample_id,
        "sample_index": sample_index,
        "seed": cfg.seed,
        "baseline": cfg.baseline,
        "baseline_kwargs": baseline_kwargs,
        "judge_model": cfg.judge_model,
        "dataset_name": f"{cfg.dataset}@1.0",
        "task_name": cfg.resolved_task(),
        "memory_sources": list(getattr(sample, "memory_sources", [])),
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
    if cfg.harness:
        # MCP-memory-on-harness experiment: memory lives under the run's output
        # dir (outputs/<exp>/<harness>/<seed>/), reused as the harness's per-
        # sample working area.
        baseline_extra = {
            "harness": cfg.harness,
            "harness_model": cfg.harness_model,
            "output_root": cfg.resolved_output_dir(),
            "batch_size": cfg.mcp_batch_size,
            "keep_memory": cfg.mcp_keep_memory,
            "max_turns": cfg.mcp_max_turns,
            "max_batch_retries": cfg.mcp_max_retries,
            "samples_per_question": cfg.samples_per_question,
            "raw_prompt": cfg.raw_prompt,
            # When --save-responses is set, MCP baselines also dump the full
            # harness transcript (thinking, tool calls, json events) to
            # harness.log alongside responses.log.
            "save_responses": cfg.save_responses,
        }
        if cfg.baseline == "pam_mcp":
            # pam_mcp builds memory server-side via Pam, so it honours the same
            # account-lifecycle knobs as the `pam` baseline.
            baseline_extra["debug_user_id"] = cfg.pam_debug_user_id
            baseline_extra["backup_memory"] = cfg.backup_memory
            # Experiment-registry preset forwarded to the memory pipeline.
            baseline_extra["pam_exp_config"] = cfg.pam_exp_config
    elif cfg.baseline == "pam":
        baseline_extra = {
            "batch_size": cfg.pam_batch_size,
            "debug_user_id": cfg.pam_debug_user_id,
            "backup_memory": cfg.backup_memory,
            # Experiment-registry preset forwarded to the memory pipeline.
            "pam_exp_config": cfg.pam_exp_config,
        }
    baseline = get_baseline(
        cfg.baseline,
        model=cfg.baseline_model,
        **{**cfg.baseline_kwargs, **baseline_extra},
    )
    await baseline.setup(seed=cfg.seed)

    # Decide which samples to process. A string --sample-id (e.g. a Harmix
    # environment id) wins over --sample-index.
    if cfg.sample_id is not None:
        if not hasattr(loader, "index_for_sample_id"):
            raise ValueError(f"--sample-id is not supported for dataset {cfg.dataset!r}")
        indices = [loader.index_for_sample_id(cfg.sample_id)]
    elif cfg.sample_index is not None:
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

    responses_log: Path | None = out_dir / "responses.log" if cfg.save_responses else None
    if responses_log is not None:
        responses_log.unlink(missing_ok=True)  # fresh log per run

    # MCP-on-harness runs land in a separate collection (<dataset>_mcp_results).
    mongo_collection = f"{cfg.dataset}_mcp_results" if cfg.harness else None

    results: list[SampleResult] = []
    with progress_for(console=console) as progress:
        for sample_index in indices:
            sample = loader.get_sample(sample_index)
            if cfg.dry_run:
                console.log(f"[yellow]dry-run[/yellow] would process {sample.sample_id}")
                continue
            processor = _process_sample_harmix if cfg.dataset == "harmix" else _process_sample
            r = await processor(
                sample, sample_index, cfg, baseline, task_runner, progress, responses_log
            )
            results.append(r)
            if cfg.mongo:
                write_sample_result(
                    dataset=cfg.dataset, document=r.document, collection=mongo_collection
                )

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
                "judge_accuracy_std": r.document.get("judge_accuracy_std"),
                "samples_per_question": r.document.get("samples_per_question"),
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
    if responses_log is not None and not cfg.dry_run:
        console.log(f"[green]Saved responses[/green] → {responses_log}")
    return overall


def run(cfg: RunConfig) -> dict[str, Any]:
    """Sync entry point — used by the CLI and any future programmatic caller."""
    console = Console()
    return asyncio.run(_run_async(cfg, console))
