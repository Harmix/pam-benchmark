"""Parser for Pam's numbered-answer batch replies."""

from __future__ import annotations

from baselines.pam.baseline import parse_batch_response


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
