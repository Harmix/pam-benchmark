"""Harmix task pipeline: drive a baseline through one environment's cases.

Harmix is an external-memory-only task: memory is built server-side from the
persona's snapshot, so every prompt is just the bare question. Mirrors the
LoCoMo pipeline's batch/lifecycle shape but drops LoCoMo's category/adversarial
shaping (Harmix has none) and carries `grading_notes` through for the judge.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from baselines.base import Baseline, BaselineResponse
from datasets.harmix.schemas import HarmixCase, HarmixSample


@dataclass
class HarmixPrediction:
    """One per-question prediction with everything the scorer/Mongo needs."""

    question_num: int
    case_id: str
    question: str
    # `None` for open/draft tasks with no single gold answer.
    expected_answer: str | None
    grading_notes: str | None
    model_answer: str
    input_tokens: int
    output_tokens: int
    est_cost_usd: float
    latency_ms: float
    prompt_tokens: int = 0
    context_tokens: int = 0
    agent_input_tokens: int = 0
    agent_output_tokens: int = 0
    agent_cache_read_tokens: int = 0
    agent_cache_write_tokens: int = 0
    enriched_user_prompt_tokens: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    raw_prompt: str = ""
    raw_response_text: str = ""


def _chunked(items: list[Any], size: int) -> Iterator[list[Any]]:
    if size <= 1:
        for item in items:
            yield [item]
        return
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _build_prediction(
    *,
    question_num: int,
    case: HarmixCase,
    prompt: str,
    response: BaselineResponse,
) -> HarmixPrediction:
    return HarmixPrediction(
        question_num=question_num,
        case_id=case.id,
        question=case.question,
        expected_answer=case.expected_answer,
        grading_notes=case.grading_notes,
        model_answer=(response.text or "").strip(),
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        est_cost_usd=response.usage.est_cost_usd,
        latency_ms=response.latency_ms,
        prompt_tokens=response.usage.prompt_tokens,
        context_tokens=response.usage.context_tokens,
        agent_input_tokens=response.usage.agent_input_tokens,
        agent_output_tokens=response.usage.agent_output_tokens,
        agent_cache_read_tokens=response.usage.agent_cache_read_tokens,
        agent_cache_write_tokens=response.usage.agent_cache_write_tokens,
        enriched_user_prompt_tokens=response.usage.enriched_user_prompt_tokens,
        raw_prompt=str(response.raw.get("raw_prompt", prompt)),
        raw_response_text=str(response.raw.get("raw_response", response.text)),
    )


async def run_sample(
    sample: HarmixSample,
    *,
    baseline: Baseline,
    seed: int,
    model_name: str,
    max_questions: int | None = None,
    on_question_done=None,
    on_batch_done=None,
) -> list[HarmixPrediction]:
    """Drive one environment (persona) through the baseline.

    Calls `prepare_for_sample` once (which builds the persona's memory from its
    snapshot), then chunks cases by `baseline.batch_size` and dispatches each
    chunk via `answer_batch`. Cleanup runs even on failure.
    """
    cases = sample.qa if max_questions is None else sample.qa[:max_questions]
    batch_size = max(1, getattr(baseline, "batch_size", 1) or 1)

    await baseline.prepare_for_sample(sample)
    out: list[HarmixPrediction] = []
    try:
        question_num = 0
        for chunk in _chunked(list(cases), batch_size):
            prompts = [c.question for c in chunk]
            responses = await baseline.answer_batch(prompts)
            if len(responses) != len(chunk):
                raise RuntimeError(
                    f"baseline.answer_batch returned {len(responses)} responses "
                    f"for {len(chunk)} prompts"
                )
            batch_preds: list[HarmixPrediction] = []
            for case, prompt, response in zip(chunk, prompts, responses, strict=True):
                question_num += 1
                prediction = _build_prediction(
                    question_num=question_num, case=case, prompt=prompt, response=response
                )
                out.append(prediction)
                batch_preds.append(prediction)
                if on_question_done is not None:
                    on_question_done(prediction)
            if on_batch_done is not None:
                on_batch_done(batch_preds)
    finally:
        await baseline.cleanup_sample()
    return out
