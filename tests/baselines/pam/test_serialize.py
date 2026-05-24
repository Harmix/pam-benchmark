"""Pam serializer — LoCoMo conversation → one JSON file."""

from __future__ import annotations

import json

from baselines.pam.serialize import serialize_sample
from datasets.locomo.schemas import LoCoMoQA, LoCoMoSample


def _make_sample() -> LoCoMoSample:
    return LoCoMoSample(
        sample_id="conv-7",
        qa=[LoCoMoQA(question="Q?", answer="A", category=1)],
        conversation={
            "speaker_a": "Alice",
            "speaker_b": "Bob",
            "session_1_date_time": "1 Jan 2024",
            "session_1": [{"speaker": "Alice", "dia_id": "D1:1", "text": "hello"}],
            "session_2_date_time": "2 Jan 2024",
            "session_2": [{"speaker": "Bob", "dia_id": "D2:1", "text": "hi"}],
        },
    )


def test_serialize_emits_single_file_named_after_sample_id():
    files = serialize_sample(_make_sample())
    assert len(files) == 1
    name, body = files[0]
    assert name == "conv-7_conversation.json"
    assert isinstance(body, bytes)


def test_serialize_payload_contains_all_session_keys():
    files = serialize_sample(_make_sample())
    payload = json.loads(files[0][1])
    assert payload["sample_id"] == "conv-7"
    assert payload["speaker_a"] == "Alice"
    assert payload["speaker_b"] == "Bob"
    assert "session_1" in payload
    assert "session_1_date_time" in payload
    assert "session_2" in payload
    assert "session_2_date_time" in payload


def test_serialize_preserves_session_order():
    sample = LoCoMoSample(
        sample_id="ordered",
        qa=[LoCoMoQA(question="Q?", answer="A", category=1)],
        conversation={
            "speaker_a": "X",
            "speaker_b": "Y",
            # Insertion order matters; both Python dicts and json.dumps preserve it.
            "session_1_date_time": "d1",
            "session_1": [],
            "session_2_date_time": "d2",
            "session_2": [],
            "session_3_date_time": "d3",
            "session_3": [],
        },
    )
    files = serialize_sample(sample)
    text = files[0][1].decode("utf-8")
    pos = [
        text.index('"session_1_date_time"'),
        text.index('"session_1"'),
        text.index('"session_2_date_time"'),
        text.index('"session_2"'),
        text.index('"session_3_date_time"'),
        text.index('"session_3"'),
    ]
    assert pos == sorted(pos), f"session ordering not preserved: {pos}"


def test_serialize_skips_missing_speakers():
    sample = LoCoMoSample(
        sample_id="no-speakers",
        qa=[LoCoMoQA(question="Q?", answer="A", category=1)],
        conversation={
            "session_1_date_time": "d1",
            "session_1": [{"speaker": "Alice", "dia_id": "D1:1", "text": "hi"}],
        },
    )
    payload = json.loads(serialize_sample(sample)[0][1])
    assert "speaker_a" not in payload
    assert "speaker_b" not in payload
    assert "session_1" in payload
