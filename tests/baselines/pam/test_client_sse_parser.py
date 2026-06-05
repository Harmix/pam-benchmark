"""PamClient SSE-stream parser — multi-turn + injected_tokens extraction."""

from __future__ import annotations

import json

from baselines.pam.client import PamClient


def _sse(payload: dict) -> str:
    return "data: " + json.dumps(payload)


def test_parser_returns_last_assistant_turn_only():
    lines = [
        _sse({"role": "assistant", "content_new": {"type": "text", "text": "thinking..."}}),
        _sse({"role": "tool_use"}),
        _sse({"role": "tool_result"}),
        _sse({"role": "assistant", "content_new": {"type": "text", "text": "Final answer."}}),
        _sse({"role": "result", "usage": {"injected_tokens": 0}}),
    ]
    text, injected = PamClient._parse_sse_stream(iter(lines))
    assert text == "Final answer."
    assert injected == 0


def test_parser_concatenates_chunks_within_a_turn():
    lines = [
        _sse({"role": "assistant", "content_new": {"type": "text", "text": "Hello "}}),
        _sse({"role": "assistant", "content_new": {"type": "text", "text": "world"}}),
        _sse({"role": "result"}),
    ]
    text, _ = PamClient._parse_sse_stream(iter(lines))
    assert text == "Hello world"


def test_parser_picks_up_injected_tokens_from_top_level():
    lines = [
        _sse({"role": "assistant", "content_new": {"type": "text", "text": "ok"}}),
        _sse({"role": "result", "injected_tokens": 2048}),
    ]
    _, injected = PamClient._parse_sse_stream(iter(lines))
    assert injected == 2048


def test_parser_picks_up_injected_tokens_from_usage():
    lines = [
        _sse({"role": "assistant", "content_new": {"type": "text", "text": "ok"}}),
        _sse({"role": "result", "usage": {"injected_tokens": 1024}}),
    ]
    _, injected = PamClient._parse_sse_stream(iter(lines))
    assert injected == 1024


def test_parser_skips_resume_conversation_and_blank_lines():
    lines = [
        "",
        _sse({"type": "resume_conversation"}),
        _sse({"role": "assistant", "content_new": {"type": "text", "text": "hi"}}),
        _sse({"role": "result"}),
    ]
    text, _ = PamClient._parse_sse_stream(iter(lines))
    assert text == "hi"


def test_parser_stops_on_stream_stopped_event():
    lines = [
        _sse({"role": "assistant", "content_new": {"type": "text", "text": "partial"}}),
        "event: stream_stopped",
        _sse({"role": "assistant", "content_new": {"type": "text", "text": "never seen"}}),
    ]
    text, _ = PamClient._parse_sse_stream(iter(lines))
    assert text == "partial"


def test_parser_ignores_malformed_json_lines():
    lines = [
        "data: this is not json",
        _sse({"role": "assistant", "content_new": {"type": "text", "text": "ok"}}),
        _sse({"role": "result"}),
    ]
    text, _ = PamClient._parse_sse_stream(iter(lines))
    assert text == "ok"


def test_parser_empty_stream_returns_empty():
    text, injected = PamClient._parse_sse_stream(iter([]))
    assert text == ""
    assert injected == 0


# --- result-frame answer (the real Pam shape) ----------------------------


def test_parser_prefers_result_frame_text_when_assistant_turns_empty():
    """Real Pam case: the final answer arrives ONLY in the terminal `result`
    frame (assistant frames were tool-use/thinking), so the parser must read
    content_new.text from the result frame instead of returning empty."""
    answer = "A1: Approximately 3 years ago (May 7, 2023)\nA2: 2022\nA3: Counseling"
    lines = [
        _sse({"role": "tool_use"}),
        _sse({"role": "tool_result"}),
        _sse({"role": "result", "content_new": {"type": "text", "text": answer}}),
    ]
    text, _ = PamClient._parse_sse_stream(iter(lines))
    assert text == answer


def test_parser_result_frame_text_wins_over_assistant_turns():
    """Even when assistant text turns exist, the aggregated result frame is the
    authoritative answer."""
    lines = [
        _sse({"role": "assistant", "content_new": {"type": "text", "text": "Let me check..."}}),
        _sse({"role": "tool_use"}),
        _sse({"role": "tool_result"}),
        _sse({"role": "assistant", "content_new": {"type": "text", "text": "A1: partial"}}),
        _sse(
            {
                "role": "result",
                "content_new": {"type": "text", "text": "A1: full\nA2: full"},
            }
        ),
    ]
    text, _ = PamClient._parse_sse_stream(iter(lines))
    assert text == "A1: full\nA2: full"


def test_parser_falls_back_to_assistant_turn_when_result_has_no_text():
    """A result frame with empty/absent text → keep the old last-turn behavior."""
    lines = [
        _sse({"role": "assistant", "content_new": {"type": "text", "text": "Final answer."}}),
        _sse({"role": "result", "content_new": {"type": "text", "text": ""}}),
    ]
    text, _ = PamClient._parse_sse_stream(iter(lines))
    assert text == "Final answer."


def test_parser_last_result_frame_wins_on_auto_continue():
    """Workflow auto-continue can emit multiple result frames; use the last."""
    lines = [
        _sse({"role": "result", "content_new": {"type": "text", "text": "first"}}),
        _sse({"role": "assistant", "content_new": {"type": "text", "text": "more work"}}),
        _sse({"role": "tool_use"}),
        _sse({"role": "result", "content_new": {"type": "text", "text": "second (final)"}}),
    ]
    text, _ = PamClient._parse_sse_stream(iter(lines))
    assert text == "second (final)"
