"""Protocol compat — both baselines satisfy the (extended) Baseline contract."""

from __future__ import annotations

import asyncio
import inspect

import pytest

from baselines.base import Baseline, BaselineBase
from baselines.litellm_baseline import LiteLLMBaseline


def test_litellm_satisfies_extended_protocol():
    b = LiteLLMBaseline(model="gpt-4-turbo")
    assert isinstance(b, Baseline)
    for hook in (
        "setup",
        "prepare_for_sample",
        "answer",
        "answer_batch",
        "cleanup_sample",
        "teardown",
    ):
        assert inspect.iscoroutinefunction(getattr(b, hook)), hook
    assert b.external_memory is False
    assert b.batch_size == 1
    assert b.extras() == {}


def test_pam_baseline_satisfies_extended_protocol(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PAM_API_HOST", "http://stub")
    monkeypatch.setenv("PAM_API_USER", "admin@stub")
    monkeypatch.setenv("PAM_API_PASSWORD", "stub-password")

    from baselines.pam.baseline import PamBaseline

    b = PamBaseline()
    assert isinstance(b, Baseline)
    assert b.external_memory is True
    assert b.batch_size == 10
    # All lifecycle hooks are coroutines
    for hook in (
        "setup",
        "prepare_for_sample",
        "answer",
        "answer_batch",
        "cleanup_sample",
        "teardown",
    ):
        assert inspect.iscoroutinefunction(getattr(b, hook)), hook


def test_baseline_base_default_answer_batch_loops_answer():
    class FakeBaseline(BaselineBase):
        name = "fake"
        track = "test"

        def __init__(self):
            self.calls: list[str] = []

        async def setup(self, *, seed: int) -> None:
            pass

        async def answer(self, prompt, *, max_tokens=None):
            from baselines.base import BaselineResponse

            self.calls.append(prompt)
            return BaselineResponse(text=f"echo:{prompt}")

        async def teardown(self) -> None:
            pass

    fb = FakeBaseline()
    results = asyncio.run(fb.answer_batch(["one", "two", "three"]))
    assert [r.text for r in results] == ["echo:one", "echo:two", "echo:three"]
    assert fb.calls == ["one", "two", "three"]
