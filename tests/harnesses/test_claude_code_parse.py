"""ClaudeCodeHarness JSON output parsing."""

from __future__ import annotations

import json

import pytest

from harnesses.claude_code.harness import ClaudeCodeHarness


def _json(**over):
    base = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": "A1: blue\nA2: green",
        "session_id": "sess-123",
        "num_turns": 3,
        "duration_ms": 4200,
        "total_cost_usd": 0.0123,
        "usage": {
            "input_tokens": 500,
            "output_tokens": 80,
            "cache_read_input_tokens": 120,
            "cache_creation_input_tokens": 30,
        },
    }
    base.update(over)
    return json.dumps(base)


def test_parse_single_json_object():
    r = ClaudeCodeHarness._parse_output(_json(), wall_ms=9999.0)
    assert r.text == "A1: blue\nA2: green"
    assert r.input_tokens == 500
    assert r.output_tokens == 80
    assert r.cache_read_tokens == 120
    assert r.cache_write_tokens == 30
    assert r.cost_usd == pytest.approx(0.0123)
    assert r.duration_ms == 4200  # prefers reported duration over wall clock
    assert r.session_id == "sess-123"
    assert r.num_turns == 3


def test_parse_ndjson_takes_last_object():
    stream = "\n".join(['{"type":"system","subtype":"init"}', _json()])
    r = ClaudeCodeHarness._parse_output(stream, wall_ms=1.0)
    assert r.text == "A1: blue\nA2: green"
    assert r.input_tokens == 500


def test_parse_missing_usage_defaults_zero():
    r = ClaudeCodeHarness._parse_output(_json(usage={}), wall_ms=10.0)
    assert r.input_tokens == 0
    assert r.output_tokens == 0


def test_parse_falls_back_to_wall_ms_when_no_duration():
    payload = json.loads(_json())
    payload.pop("duration_ms")
    r = ClaudeCodeHarness._parse_output(json.dumps(payload), wall_ms=777.0)
    assert r.duration_ms == 777.0


def test_parse_error_result_raises():
    with pytest.raises(RuntimeError):
        ClaudeCodeHarness._parse_output(_json(is_error=True, result="boom"), wall_ms=1.0)


def test_parse_unparseable_raises():
    with pytest.raises(RuntimeError):
        ClaudeCodeHarness._parse_output("not json at all", wall_ms=1.0)
