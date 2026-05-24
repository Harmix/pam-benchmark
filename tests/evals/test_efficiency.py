"""Token counting — shared by every baseline that needs prompt-side budgeting."""

from __future__ import annotations

import pytest

from evals.efficiency import count_tokens


def test_empty_text_is_zero():
    assert count_tokens("") == 0


def test_short_text_positive():
    assert count_tokens("hello world") > 0


def test_longer_text_more_tokens():
    short = count_tokens("hi")
    longer = count_tokens("hi " * 50)
    assert longer > short


def test_unknown_model_falls_back_to_cl100k():
    # Unknown models fall back to cl100k_base; should not raise.
    a = count_tokens("hello world", model="some-unknown-model-xyz")
    b = count_tokens("hello world", model="gpt-4o")
    # Both encodings are cl100k_base for this string, so should agree.
    assert a == b


@pytest.mark.parametrize("model", ["gpt-4-turbo", "gpt-4o", "gpt-3.5-turbo"])
def test_known_models_succeed(model):
    assert count_tokens("a b c d e", model=model) > 0
