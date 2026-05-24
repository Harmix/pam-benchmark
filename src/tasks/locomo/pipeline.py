"""LoCoMo task pipeline: drive a baseline through one sample's QA pairs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from baselines.base import Baseline, BaselineResponse
from datasets.locomo.schemas import CATEGORY_NAMES, LoCoMoQA, LoCoMoSample
from tasks.locomo.prompts import BuiltPrompt, build_prompt, resolve_cat5_answer


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
    raw_response: dict[str, Any] = field(default_factory=dict)


async def answer_one(
    sample: LoCoMoSample,
    qa: LoCoMoQA,
    *,
    baseline: Baseline,
    seed: int,
    model_name: str,
) -> tuple[BuiltPrompt, BaselineResponse]:
    """Build the prompt and call the baseline for one QA pair."""
    built = build_prompt(sample, qa, model=model_name, seed=seed)
    response = await baseline.answer(built.prompt)
    return built, response


def _resolve_text(built: BuiltPrompt, response: BaselineResponse) -> str:
    text = (response.text or "").strip()
    if built.cat5_answer_key:
        return resolve_cat5_answer(text, built.cat5_answer_key)
    return text


async def run_sample(
    sample: LoCoMoSample,
    *,
    baseline: Baseline,
    seed: int,
    model_name: str,
    max_questions: int | None = None,
    on_question_done=None,
) -> list[LoCoMoPrediction]:
    """Iterate every QA pair (capped at `max_questions`) and return predictions.

    `on_question_done(prediction)` fires after each completed question so the
    runner can advance progress bars / log lines.
    """
    qa_items = sample.qa if max_questions is None else sample.qa[:max_questions]
    out: list[LoCoMoPrediction] = []
    for i, qa in enumerate(qa_items, start=1):
        built, response = await answer_one(
            sample, qa, baseline=baseline, seed=seed, model_name=model_name
        )
        model_answer = _resolve_text(built, response)
        prediction = LoCoMoPrediction(
            question_num=i,
            question=qa.question,
            expected_answer=built.expected_answer,
            model_answer=model_answer,
            category=qa.category,
            category_name=CATEGORY_NAMES.get(qa.category, f"category_{qa.category}"),
            evidence=list(qa.evidence),
            is_adversarial=built.cat5_answer_key is not None,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            est_cost_usd=response.usage.est_cost_usd,
            latency_ms=response.latency_ms,
        )
        out.append(prediction)
        if on_question_done is not None:
            on_question_done(prediction)
    return out
