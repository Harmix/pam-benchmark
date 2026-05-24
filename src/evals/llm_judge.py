"""LLM-as-judge with a typed pydantic rubric.

Uses `instructor` to coerce the judge model's output into a `JudgeVerdict`
pydantic object. Provider routing happens via LiteLLM, so any LiteLLM
model identifier works as a `--judge-model`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, ClassVar

import instructor
import litellm
from pydantic import BaseModel, Field
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from evals.base import JudgeResult

logger = logging.getLogger(__name__)

JUDGE_SYSTEM_PROMPT = (
    "You are a strict, fair evaluator of question-answering systems. "
    "Compare a model's answer to a ground-truth answer for a given question. "
    "Award full credit if the model's answer captures the same factual content as the ground truth, "
    "even if phrased differently. Award no credit if the model's answer is wrong, hedges, or refuses. "
    "Award partial credit (0 < score < 1) only if the answer is partially correct. "
    "Be especially careful with dates, numbers, and named entities — these must match in substance."
)

JUDGE_USER_TEMPLATE = (
    "QUESTION:\n{question}\n\n"
    "GROUND TRUTH ANSWER:\n{ground_truth}\n\n"
    "MODEL ANSWER:\n{model_answer}\n\n"
    "Return a JSON verdict using the JudgeVerdict schema:\n"
    "- correct: true if the model answer is substantively correct, false otherwise.\n"
    "- score: 0.0 to 1.0 (use the full range; partial credit allowed).\n"
    "- confidence: 0.0 to 1.0 — how confident you are in this verdict.\n"
    "- reasoning: 1-3 short sentences justifying the verdict."
)


class JudgeVerdict(BaseModel):
    """Schema enforced on the judge model's output via `instructor`."""

    correct: bool
    score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0, default=0.9)
    reasoning: str


class _ClientHolder:
    """Cache the async instructor client per judge-model name."""

    _clients: ClassVar[dict[str, Any]] = {}

    @classmethod
    def get(cls, judge_model: str) -> Any:
        if judge_model not in cls._clients:
            cls._clients[judge_model] = instructor.from_litellm(litellm.acompletion)
        return cls._clients[judge_model]


async def judge_answer(
    *,
    question: str,
    ground_truth: str,
    model_answer: str,
    judge_model: str = "gpt-4o",
    max_attempts: int = 3,
    temperature: float = 0.0,
) -> JudgeResult:
    """Score one (question, ground_truth, model_answer) triple via LLM judge."""
    client = _ClientHolder.get(judge_model)
    messages = [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": JUDGE_USER_TEMPLATE.format(
                question=question,
                ground_truth=ground_truth or "(empty)",
                model_answer=model_answer or "(empty)",
            ),
        },
    ]

    last_exc: BaseException | None = None
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        retry=retry_if_exception_type(Exception),
        reraise=False,
    ):
        with attempt:
            verdict: JudgeVerdict = await client.chat.completions.create(
                model=judge_model,
                messages=messages,
                response_model=JudgeVerdict,
                temperature=temperature,
            )
            return JudgeResult(
                correct=verdict.correct,
                score=verdict.score,
                confidence=verdict.confidence,
                reasoning=verdict.reasoning,
                judge_model=judge_model,
                raw=verdict.model_dump(),
            )
    # If we get here, all attempts raised. Defensive fallback so a single
    # bad judge call doesn't kill a long run.
    logger.warning("LLM judge failed after %d attempts: %s", max_attempts, last_exc)
    return JudgeResult(
        correct=False,
        score=0.0,
        confidence=0.0,
        reasoning=f"judge call failed: {last_exc}",
        judge_model=judge_model,
        raw={},
    )


async def judge_many(
    triples: list[tuple[str, str, str]],
    *,
    judge_model: str = "gpt-4o",
    concurrency: int = 8,
) -> list[JudgeResult]:
    """Judge many triples concurrently with a bounded fan-out."""
    sem = asyncio.Semaphore(concurrency)

    async def _one(q: str, gt: str, ma: str) -> JudgeResult:
        async with sem:
            return await judge_answer(
                question=q, ground_truth=gt, model_answer=ma, judge_model=judge_model
            )

    return await asyncio.gather(*(_one(q, gt, ma) for q, gt, ma in triples))
