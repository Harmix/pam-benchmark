"""Baseline protocol — every system under test implements this."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    est_cost_usd: float = 0.0


@dataclass
class BaselineResponse:
    """One baseline answer to one prompt."""

    text: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    latency_ms: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Baseline(Protocol):
    """System-under-test contract.

    Lifecycle:
        await baseline.setup(seed=...)
        for prompt in prompts:
            r = await baseline.answer(prompt, max_tokens=...)
        await baseline.teardown()
    """

    name: str
    track: str  # "out_of_the_box" | "tuned"

    async def setup(self, *, seed: int) -> None: ...

    async def answer(self, prompt: str, *, max_tokens: int | None = None) -> BaselineResponse: ...

    async def teardown(self) -> None: ...
