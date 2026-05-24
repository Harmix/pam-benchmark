"""Schema-level tests for the LLM judge — no API calls."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from evals.llm_judge import JudgeVerdict


def test_valid_verdict():
    v = JudgeVerdict(correct=True, score=0.95, confidence=0.9, reasoning="exact match")
    assert v.correct is True
    assert v.score == 0.95
    assert v.confidence == 0.9


def test_score_out_of_range_rejected():
    with pytest.raises(ValidationError):
        JudgeVerdict(correct=True, score=1.5, reasoning="x")
    with pytest.raises(ValidationError):
        JudgeVerdict(correct=True, score=-0.1, reasoning="x")


def test_confidence_out_of_range_rejected():
    with pytest.raises(ValidationError):
        JudgeVerdict(correct=True, score=0.5, confidence=2.0, reasoning="x")


def test_missing_required_fields_rejected():
    with pytest.raises(ValidationError):
        JudgeVerdict(correct=True, score=0.5)  # missing reasoning


def test_confidence_defaults_to_0_9():
    v = JudgeVerdict(correct=False, score=0.0, reasoning="wrong")
    assert v.confidence == pytest.approx(0.9)
