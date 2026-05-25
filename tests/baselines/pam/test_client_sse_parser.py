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
