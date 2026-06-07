"""Baseline + dataset contract checks — protocol conformance for every system."""

from __future__ import annotations

import inspect

from baselines.base import Baseline, BaselineResponse, TokenUsage, split_input_tokens
from baselines.litellm_baseline import LiteLLMBaseline
from datasets.base import DatasetLoader
from datasets.locomo.loader import LoCoMoLoader


def test_litellm_baseline_implements_protocol():
    b = LiteLLMBaseline(model="gpt-4-turbo")
    assert isinstance(b, Baseline)
    assert hasattr(b, "name")
    assert hasattr(b, "track")
    # Async methods exist
    assert inspect.iscoroutinefunction(b.setup)
    assert inspect.iscoroutinefunction(b.answer)
    assert inspect.iscoroutinefunction(b.teardown)


def test_locomo_loader_implements_protocol():
    loader = LoCoMoLoader()
    assert isinstance(loader, DatasetLoader)


def test_token_usage_defaults_zero():
    u = TokenUsage()
    assert u.input_tokens == 0
    assert u.output_tokens == 0
    assert u.est_cost_usd == 0.0
    assert u.prompt_tokens == 0
    assert u.context_tokens == 0


def test_split_input_tokens_normal_case():
    # context = input - prompt
    assert split_input_tokens(1000, 40) == (40, 960)


def test_split_input_tokens_zero_input_forces_zero_prompt():
    # input==0 → prompt forced to 0 so context is never negative
    assert split_input_tokens(0, 40) == (0, 0)


def test_split_input_tokens_caps_prompt_at_input():
    # prompt count exceeding input (tokenizer mismatch) is capped, context >= 0
    assert split_input_tokens(30, 50) == (30, 0)


def test_baseline_response_default_usage():
    r = BaselineResponse(text="hi")
    assert r.text == "hi"
    assert r.usage.input_tokens == 0
    assert r.latency_ms == 0.0
    assert r.raw == {}


def test_litellm_setup_records_seed_in_kwargs():
    import asyncio

    b = LiteLLMBaseline(model="gpt-4-turbo")
    asyncio.run(b.setup(seed=123))
    assert b.completion_kwargs.get("seed") == 123


def test_litellm_setup_does_not_clobber_existing_seed():
    import asyncio

    b = LiteLLMBaseline(model="gpt-4-turbo", completion_kwargs={"seed": 999})
    asyncio.run(b.setup(seed=42))
    # setdefault, not overwrite — user-provided seed wins
    assert b.completion_kwargs["seed"] == 999
