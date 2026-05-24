"""Prompt builder — every baseline goes through this for LoCoMo."""

from __future__ import annotations

import pytest

from datasets.locomo.loader import LoCoMoLoader
from datasets.locomo.schemas import LoCoMoQA, LoCoMoSample
from tasks.locomo.prompts import build_prompt, resolve_cat5_answer


@pytest.fixture(scope="module")
def sample() -> LoCoMoSample:
    return LoCoMoLoader().get_sample(0)


@pytest.mark.parametrize("category", [1, 2, 3, 4, 5])
def test_build_prompt_for_each_category(sample, category):
    qa = next((q for q in sample.qa if q.category == category), None)
    if qa is None:
        pytest.skip(f"no category {category} in sample 0")
    bp = build_prompt(sample, qa, model="gpt-4-turbo", seed=42)
    assert bp.prompt
    assert bp.expected_answer is not None
    assert "Short answer:" in bp.prompt


def test_build_prompt_cat5_creates_answer_key(sample):
    qa = next(q for q in sample.qa if q.category == 5)
    bp = build_prompt(sample, qa, model="gpt-4-turbo", seed=42)
    assert bp.is_adversarial
    assert bp.cat5_answer_key is not None
    assert set(bp.cat5_answer_key.keys()) == {"a", "b"}
    # One of the options must be the correct answer
    assert bp.expected_answer in bp.cat5_answer_key.values()


def test_build_prompt_cat2_appends_date_hint(sample):
    qa = next(q for q in sample.qa if q.category == 2)
    bp = build_prompt(sample, qa, model="gpt-4-turbo", seed=42)
    assert "DATE of CONVERSATION" in bp.prompt


def test_build_prompt_seed_reproducible(sample):
    qa = next(q for q in sample.qa if q.category == 5)
    bp1 = build_prompt(sample, qa, model="gpt-4-turbo", seed=42)
    bp2 = build_prompt(sample, qa, model="gpt-4-turbo", seed=42)
    assert bp1.cat5_answer_key == bp2.cat5_answer_key


def test_build_prompt_different_seeds_may_swap_cat5_order(sample):
    """Across many cat-5 questions, two different seeds should produce at
    least one ordering difference (otherwise the randomization is broken)."""
    cat5_qa = [q for q in sample.qa if q.category == 5]
    if not cat5_qa:
        pytest.skip("no cat-5 questions in sample")
    s1 = [build_prompt(sample, q, model="gpt-4-turbo", seed=1).cat5_answer_key for q in cat5_qa]
    s2 = [build_prompt(sample, q, model="gpt-4-turbo", seed=2).cat5_answer_key for q in cat5_qa]
    assert s1 != s2


def test_build_prompt_unknown_model_falls_back():
    # Custom small sample so the test runs fast even though encoder fallback uses cl100k.
    s = LoCoMoSample(
        sample_id="t",
        qa=[LoCoMoQA(question="Q?", answer="A", category=1)],
        conversation={
            "speaker_a": "Alice",
            "speaker_b": "Bob",
            "session_1_date_time": "1 Jan 2024",
            "session_1": [{"speaker": "Alice", "dia_id": "D1:1", "text": "hello"}],
        },
    )
    bp = build_prompt(s, s.qa[0], model="some-random-model", seed=0)
    assert "Short answer:" in bp.prompt


def test_resolve_cat5_letter_to_text():
    key = {"a": "self-care is important", "b": "Not mentioned"}
    assert resolve_cat5_answer("a", key) == "self-care is important"
    assert resolve_cat5_answer("(b)", key) == "Not mentioned"
    assert resolve_cat5_answer("B", key) == "Not mentioned"  # case-insensitive
    # Free-text reply passes through unchanged
    assert resolve_cat5_answer("some free text answer", key) == "some free text answer"
