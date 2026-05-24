"""Common eval types used across datasets/baselines."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class JudgeResult:
    """Outcome of one LLM-judge call."""

    correct: bool
    score: float
    confidence: float
    reasoning: str
    judge_model: str = ""
    raw: dict = field(default_factory=dict)
