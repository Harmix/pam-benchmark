"""memory_md backend + conversation serializer."""

from __future__ import annotations

import asyncio
from pathlib import Path

from baselines.mcp.memory_md.backend import MemoryMdBackend
from baselines.mcp.serialize import conversation_to_transcript
from datasets.locomo.schemas import LoCoMoQA, LoCoMoSample


def _sample():
    return LoCoMoSample(
        sample_id="s1",
        qa=[LoCoMoQA(question="what color?", answer="blue", category=1)],
        conversation={
            "speaker_a": "Alice",
            "speaker_b": "Bob",
            "session_1_date_time": "1 Jan 2024",
            "session_1": [
                {"speaker": "Alice", "dia_id": "D1:1", "text": "the sky is blue"},
                {"speaker": "Bob", "dia_id": "D1:2", "text": "agreed"},
            ],
            "session_2_date_time": "2 Jan 2024",
            "session_2": [{"speaker": "Alice", "dia_id": "D2:1", "text": "and grass is green"}],
        },
    )


def test_transcript_has_sessions_and_turns_but_no_questions():
    t = conversation_to_transcript(_sample())
    assert "Session 1 — 1 Jan 2024" in t
    assert "Session 2 — 2 Jan 2024" in t
    assert "Alice: the sky is blue" in t
    assert "Bob: agreed" in t
    assert "and grass is green" in t
    # Fairness: the question text must never leak into the ingested memory.
    assert "what color?" not in t


def test_backend_tools_and_no_mcp_server():
    b = MemoryMdBackend()
    assert b.name == "memory_md_mcp"
    assert b.mcp_servers(Path("/tmp/x")) is None
    ingest = b.allowed_tools("ingest")
    answer = b.allowed_tools("answer")
    assert "Write" in ingest and "Edit" in ingest
    # answer phase is read-only.
    assert "Write" not in answer and "Edit" not in answer
    assert "Read" in answer


def test_ingest_prompt_excludes_questions_answer_prompt_includes_batch():
    b = MemoryMdBackend()
    ingest = b.ingest_prompt("CONVERSATION TEXT")
    assert "CONVERSATION TEXT" in ingest
    assert "MEMORY_WRITTEN" in ingest
    answer = b.answer_prompt("Q1: foo")
    assert "Q1: foo" in answer


def test_reset_and_memory_exists(tmp_path):
    b = MemoryMdBackend()
    mem = tmp_path / "memory"
    notes = mem / "notes"
    notes.mkdir(parents=True)
    (notes / "a.md").write_text("x")
    (mem / "index.md").write_text("idx")
    assert b.memory_exists(mem) is True
    asyncio.run(b.reset(mem))
    assert b.memory_exists(mem) is False
