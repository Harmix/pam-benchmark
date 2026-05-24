"""Async LiteLLM completion wrapper with retries and rate limiting.

Centralizes the only path through which baselines and the LLM judge call any
LLM. Keeps retry policy, rate limiting, and usage extraction in one place.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import litellm
from aiolimiter import AsyncLimiter
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# Per-process registry of (model -> limiter). Sized lazily on first use.
_limiters: dict[str, AsyncLimiter] = {}
_limiters_lock = asyncio.Lock()

# Default rate limit (requests per minute) when none is supplied. The 50 RPM
# default targets gpt-4-turbo's lower tier; baselines can override per-call.
DEFAULT_RPM = 50


async def _get_limiter(key: str, rpm: int) -> AsyncLimiter:
    async with _limiters_lock:
        limiter = _limiters.get(key)
        if limiter is None or limiter.max_rate != rpm:
            limiter = AsyncLimiter(rpm, time_period=60)
            _limiters[key] = limiter
        return limiter


# Exception classes that warrant a retry. Litellm wraps provider errors;
# the catch-all on `Exception` for read timeouts is acceptable because the
# retry count is small.
_RETRYABLE: tuple[type[BaseException], ...] = tuple(
    cls
    for cls in (
        getattr(litellm, "APIConnectionError", None),
        getattr(litellm, "APIError", None),
        getattr(litellm, "RateLimitError", None),
        getattr(litellm, "ServiceUnavailableError", None),
        getattr(litellm, "Timeout", None),
        getattr(litellm, "InternalServerError", None),
    )
    if cls is not None
)


@dataclass
class CompletionResult:
    """Result of one LLM call.

    `raw` is the provider-shaped response object as a dict (for debugging or
    Mongo storage); `text` is the convenience first-choice content.
    """

    text: str
    input_tokens: int
    output_tokens: int
    model: str
    raw: dict[str, Any]


def _extract_usage(response: Any) -> tuple[int, int]:
    usage = getattr(response, "usage", None) or {}
    if hasattr(usage, "model_dump"):
        usage = usage.model_dump()
    elif hasattr(usage, "__dict__"):
        usage = dict(usage.__dict__)
    return int(usage.get("prompt_tokens", 0) or 0), int(usage.get("completion_tokens", 0) or 0)


def _response_to_dict(response: Any) -> dict[str, Any]:
    if hasattr(response, "model_dump"):
        try:
            return response.model_dump()
        except Exception:
            pass
    if hasattr(response, "to_dict"):
        try:
            return response.to_dict()
        except Exception:
            pass
    try:
        return dict(response)
    except Exception:
        return {"repr": repr(response)}


async def acompletion(
    *,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int | None = None,
    temperature: float = 0.0,
    rpm: int = DEFAULT_RPM,
    limiter_key: str | None = None,
    max_attempts: int = 5,
    extra_kwargs: dict[str, Any] | None = None,
) -> CompletionResult:
    """Single LiteLLM completion with retry + rate-limit.

    Args:
        model: LiteLLM model name (e.g. "gpt-4-turbo", "gpt-4o", "claude-3-5-sonnet").
        messages: OpenAI-style messages array.
        max_tokens: cap on output tokens.
        temperature: sampling temperature (default 0 for determinism where supported).
        rpm: requests-per-minute cap for this `limiter_key`.
        limiter_key: separate rate-limit bucket; defaults to `model`.
        max_attempts: tenacity retry count.
        extra_kwargs: extra arguments forwarded verbatim to `litellm.acompletion`.
    """
    key = limiter_key or model
    limiter = await _get_limiter(key, rpm)
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if extra_kwargs:
        payload.update(extra_kwargs)

    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(_RETRYABLE)
        if _RETRYABLE
        else retry_if_exception_type(Exception),
        reraise=True,
    ):
        with attempt:
            async with limiter:
                response = await litellm.acompletion(**payload)

    text = ""
    try:
        text = (response.choices[0].message.content or "").strip()
    except Exception:
        text = ""

    in_tok, out_tok = _extract_usage(response)
    return CompletionResult(
        text=text,
        input_tokens=in_tok,
        output_tokens=out_tok,
        model=model,
        raw=_response_to_dict(response),
    )
