"""Pam serializer — LoCoMo conversation → one readable transcript (.txt)."""

from __future__ import annotations

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


def test_serialize_emits_single_txt_named_after_sample_id():
    files = serialize_sample(_make_sample())
    assert len(files) == 1
    name, body = files[0]
    assert name == "conv-7_conversation.txt"
    assert isinstance(body, bytes)


def test_serialize_renders_readable_transcript():
    text = serialize_sample(_make_sample())[0][1].decode("utf-8")
    assert "Conversation between Alice and Bob." in text
    # Sessions rendered with their date as headers, turns as "<speaker>: <text>".
    assert "=== Session 1 — 1 Jan 2024 ===" in text
    assert "=== Session 2 — 2 Jan 2024 ===" in text
    assert "Alice: hello" in text
    assert "Bob: hi" in text
    # No raw JSON structure leaks through.
    assert "dia_id" not in text
    assert "{" not in text


def test_serialize_preserves_session_order():
    sample = LoCoMoSample(
        sample_id="ordered",
        qa=[LoCoMoQA(question="Q?", answer="A", category=1)],
        conversation={
            "speaker_a": "X",
            "speaker_b": "Y",
            "session_1_date_time": "d1",
            "session_1": [{"speaker": "X", "dia_id": "D1:1", "text": "one"}],
            "session_2_date_time": "d2",
            "session_2": [{"speaker": "Y", "dia_id": "D2:1", "text": "two"}],
            "session_3_date_time": "d3",
            "session_3": [{"speaker": "X", "dia_id": "D3:1", "text": "three"}],
        },
    )
    text = serialize_sample(sample)[0][1].decode("utf-8")
    pos = [
        text.index("=== Session 1"),
        text.index("=== Session 2"),
        text.index("=== Session 3"),
    ]
    assert pos == sorted(pos), f"session ordering not preserved: {pos}"


def test_serialize_folds_in_image_captions():
    sample = LoCoMoSample(
        sample_id="img",
        qa=[LoCoMoQA(question="Q?", answer="A", category=1)],
        conversation={
            "speaker_a": "Alice",
            "speaker_b": "Bob",
            "session_1_date_time": "d1",
            "session_1": [
                {
                    "speaker": "Alice",
                    "dia_id": "D1:1",
                    "text": "Look at this!",
                    "blip_caption": "a photo of a sunrise",
                    "img_url": ["https://example.com/x.jpg"],
                }
            ],
        },
    )
    text = serialize_sample(sample)[0][1].decode("utf-8")
    assert "Alice: Look at this! [shared a photo: a photo of a sunrise]" in text


def test_serialize_skips_missing_speakers():
    sample = LoCoMoSample(
        sample_id="no-speakers",
        qa=[LoCoMoQA(question="Q?", answer="A", category=1)],
        conversation={
            "session_1_date_time": "d1",
            "session_1": [{"speaker": "Alice", "dia_id": "D1:1", "text": "hi"}],
        },
    )
    text = serialize_sample(sample)[0][1].decode("utf-8")
    assert "Conversation between" not in text
    assert "=== Session 1 — d1 ===" in text
    assert "Alice: hi" in text
