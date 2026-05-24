"""Generic LiteLLM baseline — drives any LiteLLM-supported model."""

from __future__ import annotations

from typing import Any

import litellm

from baselines.base import Baseline, BaselineResponse, TokenUsage
from utils.llm import DEFAULT_RPM, acompletion
from utils.timing import timed


class LiteLLMBaseline(Baseline):
    """Single-call baseline backed by LiteLLM.

    `model` is any LiteLLM-supported model identifier (e.g. "gpt-4-turbo",
    "gpt-4o", "anthropic/claude-3-5-sonnet"). M1 uses "gpt-4-turbo".

    All knobs (temperature, top_p, max_tokens) flow through `**completion_kwargs`
    so the same class serves the M2+ competitors that just need different model
    names and configs.
    """

    track = "out_of_the_box"

    def __init__(
        self,
        model: str,
        *,
        name: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = 1024,
        rpm: int = DEFAULT_RPM,
        completion_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self.name = name or model
        self.model = model
        self.temperature = temperature
        self.default_max_tokens = max_tokens
        self.rpm = rpm
        self.completion_kwargs = completion_kwargs or {}

    async def setup(self, *, seed: int) -> None:
        # litellm uses provider-side determinism where the provider supports it.
        # The `seed` arg is accepted by some providers; we pass it through.
        self.completion_kwargs.setdefault("seed", seed)

    async def answer(self, prompt: str, *, max_tokens: int | None = None) -> BaselineResponse:
        with timed() as t:
            result = await acompletion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens if max_tokens is not None else self.default_max_tokens,
                temperature=self.temperature,
                rpm=self.rpm,
                extra_kwargs=self.completion_kwargs,
            )
        cost = _estimate_cost(self.model, result.input_tokens, result.output_tokens)
        return BaselineResponse(
            text=result.text,
            usage=TokenUsage(
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                est_cost_usd=cost,
            ),
            latency_ms=t.ms,
            raw=result.raw,
        )

    async def teardown(self) -> None:
        return None


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Best-effort USD cost estimate from LiteLLM's pricing table."""
    try:
        return float(
            litellm.completion_cost(
                model=model,
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
            )
        )
    except Exception:
        return 0.0
