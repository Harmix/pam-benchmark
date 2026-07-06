"""The grading-notes-aware judge injects notes into the prompt (Harmix)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

import evals.llm_judge as judge_mod
from evals.llm_judge import judge_answer, judge_many_with_notes


class _FakeCompletions:
    def __init__(self, captured: list[dict[str, Any]]):
        self._captured = captured

    async def create(self, *, model, messages, response_model, temperature):
        self._captured.append({"model": model, "messages": messages})
        return judge_mod.JudgeVerdict(correct=True, score=1.0, confidence=0.9, reasoning="ok")


class _FakeClient:
    def __init__(self, captured: list[dict[str, Any]]):
        self.chat = type("chat", (), {"completions": _FakeCompletions(captured)})()


@pytest.fixture
def captured(monkeypatch):
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(judge_mod._ClientHolder, "get", lambda judge_model: _FakeClient(calls))
    return calls


def _user_text(call: dict[str, Any]) -> str:
    return call["messages"][1]["content"]


def test_grading_notes_injected_when_present(captured):
    asyncio.run(
        judge_answer(
            question="When did Yaroslav join?",
            ground_truth="Nov 11, 2025",
            model_answer="November 2025",
            judge_model="claude-sonnet-4-5",
            grading_notes="Must disambiguate the two people named Yaroslav.",
        )
    )
    text = _user_text(captured[0])
    assert "GRADING NOTES" in text
    assert "disambiguate the two people named Yaroslav" in text
    # Notes appear before the schema instructions.
    assert text.index("GRADING NOTES") < text.index("Return a JSON verdict")


def test_no_grading_notes_block_when_absent(captured):
    asyncio.run(
        judge_answer(
            question="Birth date?",
            ground_truth="20/09/2002",
            model_answer="20/09/2002",
            judge_model="claude-sonnet-4-5",
        )
    )
    assert "GRADING NOTES" not in _user_text(captured[0])


def test_judge_many_with_notes_threads_per_item(captured):
    items = [
        ("q1", "gt1", "ma1", "note-1"),
        ("q2", "gt2", "ma2", None),
    ]
    results = asyncio.run(
        judge_many_with_notes(items, judge_model="claude-sonnet-4-5", concurrency=2)
    )
    assert len(results) == 2
    texts = sorted(_user_text(c) for c in captured)
    # exactly one prompt carries the notes block.
    assert sum("GRADING NOTES" in t for t in texts) == 1
