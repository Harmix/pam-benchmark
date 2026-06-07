"""Baseline protocol — every system under test implements this."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    est_cost_usd: float = 0.0
    # External-memory baselines (e.g. Pam) report how many tokens the retriever
    # pulled from memory and fed to the answering model. LiteLLM leaves this 0.
    injected_tokens: int = 0
    # `prompt_tokens` = tokens of the question prompt sent to the model.
    # `context_tokens` = input_tokens - prompt_tokens (the rest of the input,
    # e.g. system/template/retrieved context). See `split_input_tokens`.
    prompt_tokens: int = 0
    context_tokens: int = 0


def split_input_tokens(input_tokens: int, prompt_tokens: int) -> tuple[int, int]:
    """Return `(prompt_tokens, context_tokens)` for a response.

    `context_tokens` is `input_tokens - prompt_tokens`. When `input_tokens` is 0
    (the baseline doesn't expose input usage), `prompt_tokens` is forced to 0 too
    so `context_tokens` never goes negative. `prompt_tokens` is also capped at
    `input_tokens` for the same reason.
    """
    if input_tokens <= 0:
        return 0, 0
    prompt_tokens = max(0, min(prompt_tokens, input_tokens))
    return prompt_tokens, input_tokens - prompt_tokens


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
        for sample in samples:
            await baseline.prepare_for_sample(sample)
            for chunk in chunks(sample.qa, baseline.batch_size):
                rs = await baseline.answer_batch([prompt_for(qa) for qa in chunk])
            await baseline.cleanup_sample()
        await baseline.teardown()

    `prepare_for_sample`, `cleanup_sample`, and `answer_batch` have sensible
    defaults in `BaselineBase` so single-call baselines (LiteLLM) need only
    implement `answer`.
    """

    name: str
    track: str  # "out_of_the_box" | "memory_product" | ...

    # When True, the harness skips conversation-packing and passes a bare
    # question prompt — the baseline already has the conversation in memory.
    external_memory: bool

    # How many questions the baseline answers per `answer_batch` call.
    # `1` = the harness loops `answer()` (LiteLLM behavior).
    batch_size: int

    async def setup(self, *, seed: int) -> None: ...

    async def prepare_for_sample(self, sample: Any) -> None: ...

    async def answer(self, prompt: str, *, max_tokens: int | None = None) -> BaselineResponse: ...

    async def answer_batch(self, prompts: list[str]) -> list[BaselineResponse]: ...

    async def cleanup_sample(self) -> None: ...

    async def teardown(self) -> None: ...

    def extras(self) -> dict[str, Any]: ...


class BaselineBase:
    """Default implementations for the optional hooks.

    Subclasses MUST override `setup`, `answer`, and `teardown`. They MAY
    override `prepare_for_sample` / `cleanup_sample` / `answer_batch` /
    `extras` when they need them (Pam does; LiteLLM doesn't).
    """

    external_memory: bool = False
    batch_size: int = 1

    async def prepare_for_sample(self, sample: Any) -> None:
        return None

    async def cleanup_sample(self) -> None:
        return None

    async def answer_batch(self, prompts: list[str]) -> list[BaselineResponse]:
        out: list[BaselineResponse] = []
        for prompt in prompts:
            out.append(await self.answer(prompt))  # type: ignore[attr-defined]
        return out

    def extras(self) -> dict[str, Any]:
        return {}
