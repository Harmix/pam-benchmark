"""ClaudeCodeHarness JSON output parsing."""

from __future__ import annotations

import json

import pytest

from harnesses.claude_code.harness import ClaudeCodeHarness, _dead_mcp_tool


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


# --- MCP connection health detection (_dead_mcp_tool) -------------------------

_TOOL = "mcp__pam_memory__retrieve_memory"


def _assistant_tool_use(tool_use_id: str, name: str = _TOOL) -> str:
    return json.dumps(
        {
            "type": "assistant",
            "message": {"content": [{"type": "tool_use", "id": tool_use_id, "name": name}]},
        }
    )


def _tool_result(tool_use_id: str, *, error: bool) -> str:
    content = (
        f"<tool_use_error>Error: No such tool available: {_TOOL}</tool_use_error>"
        if error
        else "Retrieved: Caroline attended the LGBTQ support group on 2023-05-06."
    )
    return json.dumps(
        {
            "type": "user",
            "message": {
                "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": content}]
            },
        }
    )


def test_dead_mcp_tool_all_calls_unavailable():
    """Every call to the required tool errored → the tool is dead (retry)."""
    stream = "\n".join(
        line
        for i in range(3)
        for line in (_assistant_tool_use(f"t{i}"), _tool_result(f"t{i}", error=True))
    )
    assert _dead_mcp_tool(stream, [_TOOL]) == _TOOL


def test_dead_mcp_tool_recovered_midrun_is_healthy():
    """Early calls errored but a later one succeeded (server connected) → healthy."""
    stream = "\n".join(
        [
            _assistant_tool_use("t0"),
            _tool_result("t0", error=True),
            _assistant_tool_use("t1"),
            _tool_result("t1", error=False),
        ]
    )
    assert _dead_mcp_tool(stream, [_TOOL]) is None


def test_dead_mcp_tool_never_called_is_healthy():
    stream = _assistant_tool_use("t0", name="SomethingElse")
    assert _dead_mcp_tool(stream, [_TOOL]) is None


def test_dead_mcp_tool_no_mcp_tools():
    assert _dead_mcp_tool("anything", []) is None
