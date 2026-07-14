"""Shared pytest fixtures.

These fixtures synthesize the dataclasses/protocol values that several
test modules consume so per-test setup stays small.
"""

from __future__ import annotations

import pytest

from baselines.base import BaselineResponse, TokenUsage
from evals.base import JudgeResult
from tasks.locomo.pipeline import LoCoMoPrediction


def pytest_collection_modifyitems(config, items):
    """Auto-tag Harmix tests with the ``harmix`` marker.

    The Harmix dataset (``src/datasets/harmix/data/``) is gitignored and not
    pushed to GitHub for privacy, so its data-loading tests can't run in CI.
    Any test whose node id mentions ``harmix`` (a ``tests/.../harmix`` path or a
    ``*harmix*`` test name) is tagged here so CI can skip them via
    ``pytest -m "not harmix"`` — new Harmix tests are covered automatically.
    """
    harmix = pytest.mark.harmix
    for item in items:
        if "harmix" in item.nodeid.lower():
            item.add_marker(harmix)


def make_prediction(
    *,
    question_num: int = 1,
    question: str = "Q?",
    expected: str = "expected",
    answer: str = "answer",
    category: int = 1,
    category_name: str = "single_hop",
    evidence: list[str] | None = None,
    is_adversarial: bool = False,
    input_tokens: int = 1000,
    output_tokens: int = 25,
    est_cost_usd: float = 0.01,
    latency_ms: float = 1500.0,
    **token_fields: int,
) -> LoCoMoPrediction:
    return LoCoMoPrediction(
        question_num=question_num,
        question=question,
        expected_answer=expected,
        model_answer=answer,
        category=category,
        category_name=category_name,
        evidence=evidence if evidence is not None else ["D1:3"],
        is_adversarial=is_adversarial,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        est_cost_usd=est_cost_usd,
        latency_ms=latency_ms,
        # prompt/context/agent_* token fields all default to 0; tests pass them
        # through by keyword when they need to exercise the new aggregations.
        **token_fields,
    )


def make_judge(*, correct: bool = True, score: float = 1.0, reasoning: str = "ok") -> JudgeResult:
    return JudgeResult(
        correct=correct,
        score=score,
        confidence=0.9,
        reasoning=reasoning,
        judge_model="gpt-4o",
    )


@pytest.fixture
def prediction_factory():
    return make_prediction


@pytest.fixture
def judge_factory():
    return make_judge


@pytest.fixture
def baseline_response_factory():
    def _f(text: str = "answer", **kwargs) -> BaselineResponse:
        usage = TokenUsage(
            input_tokens=kwargs.pop("input_tokens", 1000),
            output_tokens=kwargs.pop("output_tokens", 25),
            est_cost_usd=kwargs.pop("est_cost_usd", 0.01),
        )
        return BaselineResponse(
            text=text,
            usage=usage,
            latency_ms=kwargs.pop("latency_ms", 1500.0),
            raw=kwargs.pop("raw", {}),
        )

    return _f
