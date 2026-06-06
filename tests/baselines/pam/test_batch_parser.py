"""Parser for Pam's numbered-answer batch replies."""

from __future__ import annotations

from baselines.pam.baseline import _render_batch_prompt, parse_batch_response


def test_parser_extracts_clean_answers():
    text = """A1: forty-two
A2: blue
A3: 2024-01-05"""
    out = parse_batch_response(text, 3)
    assert out == ["forty-two", "blue", "2024-01-05"]


def test_parser_handles_continuation_lines():
    text = """A1: one
two
A2: three"""
    out = parse_batch_response(text, 2)
    assert out == ["one two", "three"]


def test_parser_tolerates_dot_or_paren_separator():
    text = """A1. alpha
A2) beta
A3: gamma"""
    out = parse_batch_response(text, 3)
    assert out == ["alpha", "beta", "gamma"]


def test_parser_missing_slot_is_empty_string():
    text = """A1: only one"""
    out = parse_batch_response(text, 3)
    assert out == ["only one", "", ""]


def test_parser_out_of_order_indices():
    text = """A3: third
A1: first
A2: second"""
    out = parse_batch_response(text, 3)
    assert out == ["first", "second", "third"]


def test_parser_ignores_preamble_text():
    text = """Sure! Here are the answers:
A1: first
A2: second"""
    out = parse_batch_response(text, 2)
    assert out == ["first", "second"]


def test_parser_case_insensitive_prefix():
    text = """a1: lower
A2: upper"""
    out = parse_batch_response(text, 2)
    assert out == ["lower", "upper"]


def test_parser_strips_reasoning_scaffold_glued_to_first_answer():
    """Real Pam case: the SSE stream began mid-thought, so the reasoning text +
    </think><final> tags are glued onto the A1 line, knocking `A1:` off the line
    start. Slot 1 must still be recovered."""
    text = (
        "` will be seen by the user. Let's output it exactly as requested."
        "</think><final>A1: Progressive/liberal\n"
        "A2: Lake sunrise\n"
        "A3: Luna, Oliver, Bailey"
    )
    out = parse_batch_response(text, 3)
    assert out == ["Progressive/liberal", "Lake sunrise", "Luna, Oliver, Bailey"]


def test_parser_strips_balanced_think_block():
    text = """<think>let me reason about Q1</think>
A1: first
A2: second"""
    out = parse_batch_response(text, 2)
    assert out == ["first", "second"]


def test_parser_strips_final_wrapper_tags():
    text = "<final>A1: first\nA2: second</final>"
    out = parse_batch_response(text, 2)
    assert out == ["first", "second"]


def test_parser_unaffected_when_no_scaffold():
    text = """A1: plain
A2: answers"""
    out = parse_batch_response(text, 2)
    assert out == ["plain", "answers"]


def test_parser_recovers_dropped_a_prefix_on_next_slot():
    """Real Pam case (Q39): the model wrote "9:" instead of "A9:", so the answer
    was being absorbed into A8. The bare next-slot number must be recovered as
    its own answer."""
    text = """A8: She painted a sunset.
9: Pottery, painting, camping, museum, swimming, hiking
A10: By attending support groups."""
    out = parse_batch_response(text, 10)
    assert out[7] == "She painted a sunset."
    assert out[8] == "Pottery, painting, camping, museum, swimming, hiking"
    assert out[9] == "By attending support groups."


def test_parser_bare_number_not_next_slot_is_continuation():
    """A numbered list item inside an answer (not the next expected slot) stays a
    continuation, it does not hijack a new answer slot."""
    text = """A1: Top picks:
3: not a new answer
A2: second"""
    out = parse_batch_response(text, 2)
    assert out == ["Top picks: 3: not a new answer", "second"]


def test_parser_bare_first_slot_recovered():
    text = """1: first
A2: second"""
    out = parse_batch_response(text, 2)
    assert out == ["first", "second"]


def test_render_batch_prompt_is_well_formed():
    prompt = _render_batch_prompt(["What color?", "What size?"])
    # No stray quote artifacts, questions and answer template both present.
    assert '\n"' not in prompt
    assert "A1: <short answer>" in prompt
    assert "A2: <short answer>" in prompt
    assert "Q1: What color?" in prompt
    assert "Q2: What size?" in prompt
    assert "A1..A2" in prompt
