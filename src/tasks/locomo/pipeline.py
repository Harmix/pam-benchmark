"""LoCoMo task pipeline: drive a baseline through one sample's QA pairs."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any

from baselines.base import Baseline, BaselineResponse
from datasets.locomo.schemas import CATEGORY_NAMES, LoCoMoQA, LoCoMoSample
from tasks.locomo.prompts import BuiltPrompt, build_bare_prompt, build_prompt, resolve_cat5_answer


@dataclass
class LoCoMoPrediction:
    """One per-question prediction with everything the scorer/Mongo needs."""

    question_num: int
    question: str
    expected_answer: str
    model_answer: str
    category: int
    category_name: str
    evidence: list[str]
    is_adversarial: bool
    input_tokens: int
    output_tokens: int
    est_cost_usd: float
    latency_ms: float
    injected_tokens: int = 0
    prompt_tokens: int = 0
    context_tokens: int = 0
    # Agent-side token usage (Pam only; from its message_metrics row).
    agent_input_tokens: int = 0
    agent_output_tokens: int = 0
    agent_cache_read_tokens: int = 0
    agent_cache_write_tokens: int = 0
    enriched_user_prompt_tokens: int = 0
    raw_response: dict[str, Any] = field(default_factory=dict)
    # Exact model in/out for the --save-responses debug log. `raw_prompt` is the
    # string actually sent to the model (the rendered batch prompt for Pam);
    # `raw_response_text` is the full model output before parsing/resolution.
    raw_prompt: str = ""
    raw_response_text: str = ""


def _build_one(
    sample: LoCoMoSample,
    qa: LoCoMoQA,
    *,
    seed: int,
    model_name: str,
    external_memory: bool,
) -> BuiltPrompt:
    if external_memory:
        return build_bare_prompt(qa, sample=sample, seed=seed)
    return build_prompt(sample, qa, model=model_name, seed=seed)


def _chunked(items: list[Any], size: int) -> Iterator[list[Any]]:
    if size <= 1:
        for item in items:
            yield [item]
        return
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _resolve_text(built: BuiltPrompt, response: BaselineResponse) -> str:
    text = (response.text or "").strip()
    if built.cat5_answer_key:
        return resolve_cat5_answer(text, built.cat5_answer_key)
    return text


async def answer_one(
    sample: LoCoMoSample,
    qa: LoCoMoQA,
    *,
    baseline: Baseline,
    seed: int,
    model_name: str,
) -> tuple[BuiltPrompt, BaselineResponse]:
    """Build the prompt and call the baseline for one QA pair.

    Kept for callers that want the simple one-shot interface; the batched
    pipeline below is what `run_sample` uses.
    """
    built = _build_one(
        sample, qa, seed=seed, model_name=model_name, external_memory=baseline.external_memory
    )
    response = await baseline.answer(built.prompt)
    return built, response


def _build_prediction(
    *,
    question_num: int,
    qa: LoCoMoQA,
    built: BuiltPrompt,
    response: BaselineResponse,
) -> LoCoMoPrediction:
    return LoCoMoPrediction(
        question_num=question_num,
        question=qa.question,
        expected_answer=built.expected_answer,
        model_answer=_resolve_text(built, response),
        category=qa.category,
        category_name=CATEGORY_NAMES.get(qa.category, f"category_{qa.category}"),
        evidence=list(qa.evidence),
        is_adversarial=built.cat5_answer_key is not None,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        est_cost_usd=response.usage.est_cost_usd,
        latency_ms=response.latency_ms,
        injected_tokens=response.usage.injected_tokens,
        prompt_tokens=response.usage.prompt_tokens,
        context_tokens=response.usage.context_tokens,
        agent_input_tokens=response.usage.agent_input_tokens,
        agent_output_tokens=response.usage.agent_output_tokens,
        agent_cache_read_tokens=response.usage.agent_cache_read_tokens,
        agent_cache_write_tokens=response.usage.agent_cache_write_tokens,
        enriched_user_prompt_tokens=response.usage.enriched_user_prompt_tokens,
        raw_prompt=str(response.raw.get("raw_prompt", built.prompt)),
        raw_response_text=str(response.raw.get("raw_response", response.text)),
    )


async def run_sample(
    sample: LoCoMoSample,
    *,
    baseline: Baseline,
    seed: int,
    model_name: str,
    max_questions: int | None = None,
    on_question_done=None,
    on_batch_done=None,
) -> list[LoCoMoPrediction]:
    """Drive one sample through the baseline.

    Calls `prepare_for_sample` once, then chunks questions by `baseline.batch_size`
    and dispatches each chunk via `answer_batch`. Cleanup runs even on failure.
    `on_question_done(prediction)` fires after each completed question so the
    runner can advance progress bars / log lines. `on_batch_done(predictions)`
    fires once per chunk with all of that chunk's predictions — the chunk shares
    one model prompt/response, so this is the right granularity for the raw-
    exchange debug log.
    """
    qa_items = sample.qa if max_questions is None else sample.qa[:max_questions]
    batch_size = max(1, getattr(baseline, "batch_size", 1) or 1)

    await baseline.prepare_for_sample(sample)
    out: list[LoCoMoPrediction] = []
    try:
        question_num = 0
        for chunk in _chunked(list(qa_items), batch_size):
            builts = [
                _build_one(
                    sample,
                    qa,
                    seed=seed,
                    model_name=model_name,
                    external_memory=baseline.external_memory,
                )
                for qa in chunk
            ]
            responses = await baseline.answer_batch([b.prompt for b in builts])
            if len(responses) != len(chunk):
                raise RuntimeError(
                    f"baseline.answer_batch returned {len(responses)} responses "
                    f"for {len(chunk)} prompts"
                )
            batch_preds: list[LoCoMoPrediction] = []
            for qa, built, response in zip(chunk, builts, responses, strict=True):
                question_num += 1
                prediction = _build_prediction(
                    question_num=question_num, qa=qa, built=built, response=response
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


def iter_predictions(items: Iterable[LoCoMoPrediction]) -> list[LoCoMoPrediction]:
    """Materialize an iterable of predictions — kept for forward-compat hooks."""
    return list(items)
