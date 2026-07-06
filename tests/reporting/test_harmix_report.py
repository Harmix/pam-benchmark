"""Harmix report path — judge-only context builder + HTML/MD render.

Guards against the LoCoMo-shaped template (F1/categories) being used for harmix
docs, which have no `f1_score` / `category_name` and carry `grading_notes`.
"""

from __future__ import annotations

from typing import Any

from reporting.html import build_report_context, render
from reporting.markdown import render_markdown


def _qa(
    n: int,
    *,
    expected: str | None,
    judged: bool,
    correct: bool = False,
    score: float = 0.0,
    notes: str | None = None,
) -> dict[str, Any]:
    return {
        "question_num": n,
        "case_id": f"oleksandr-{n:02d}",
        "question": f"q{n}",
        "expected_answer": expected,
        "model_answer": f"a{n}",
        "grading_notes": notes,
        "judged": judged,
        "judge_correct": correct if judged else None,
        "judge_score": score if judged else None,
        "judge_confidence": 0.9 if judged else None,
        "judge_reasoning": "because" if judged else None,
        "input_tokens": 1200,
        "output_tokens": 80,
        "prompt_tokens": 40,
        "context_tokens": 1100,
        "agent_input_tokens": 1000,
        "agent_output_tokens": 80,
        "agent_cache_read_tokens": 500,
        "agent_cache_write_tokens": 50,
        "est_cost_usd": 0.01,
        "latency_ms": 3000.0,
    }


def _doc() -> dict[str, Any]:
    qa = [
        _qa(1, expected="gold1", judged=True, correct=True, score=1.0),
        _qa(2, expected=None, judged=False),  # open/draft — excluded from accuracy
        _qa(3, expected="gold3", judged=True, correct=False, score=0.2, notes="disambiguate"),
    ]
    return {
        "sample_id": "oleksandr",
        "baseline": "pam_mcp",
        "seed": 42,
        "judge_model": "claude-sonnet-4-5",
        "dataset_name": "harmix@1.0",
        "batch_size": 1,
        "total_questions": 3,
        "judged_count": 2,
        "unjudged_count": 1,
        "judge_accuracy": 0.5,
        "judge_correct_count": 1,
        "total_cost_usd": 0.03,
        "total_input_tokens": 3600,
        "total_output_tokens": 240,
        "total_context_tokens": 3300,
        "avg_latency_ms": 3000.0,
        "p50_latency_ms": 3000.0,
        "p95_latency_ms": 3000.0,
        "memory_creation_duration_sec": 180.0,
        "execution_time_seconds": 45.0,
        "qa_responses": qa,
    }


def test_harmix_context_headline_uses_judged_denominator():
    ctx = build_report_context(dataset="harmix", exp_name="e", docs=[_doc()])
    assert ctx["is_harmix"] is True
    h = ctx["headline"]
    assert h["judge_correct"] == 1
    assert h["judged"] == 2  # denominator excludes the open case
    assert h["unjudged"] == 1
    assert h["judge_accuracy_pct"] == 50.0


def test_harmix_responses_include_all_verdicts():
    ctx = build_report_context(dataset="harmix", exp_name="e", docs=[_doc()])
    resp = ctx["responses"]
    # every question is present (correct + incorrect + unjudged), in order
    assert [(r["question_num"], r["verdict"]) for r in resp] == [
        (1, "correct"),
        (2, "unjudged"),
        (3, "incorrect"),
    ]
    assert ctx["verdict_filters"] == [
        {"name": "correct", "count": 1},
        {"name": "incorrect", "count": 1},
        {"name": "unjudged", "count": 1},
    ]
    assert ctx["persona_filters"] == [{"name": "oleksandr", "count": 3}]


def test_harmix_html_renders_all_responses_with_verdict_filter():
    html = render(build_report_context(dataset="harmix", exp_name="e", docs=[_doc()]))
    # no LoCoMo F1/category leakage
    assert "Token-level F1" not in html
    assert "Per-category breakdown" not in html
    assert "Per-persona results" in html
    # all responses shown with a verdict filter (default view = all)
    assert "Responses (3)" in html
    assert 'data-verdict="all"' in html
    assert 'data-verdict="correct"' in html
    assert 'data-verdict="incorrect"' in html
    assert 'data-verdict="unjudged"' in html
    assert "Unjudged (open task)" in html  # open case is included
    assert "disambiguate" in html  # grading notes surfaced on the card


def test_harmix_markdown_renders():
    md = render_markdown(dataset="harmix", exp_name="e", docs=[_doc()])
    assert "LLM-judge accuracy: **50.0%** (1/2 judged)" in md
    assert "open/unjudged: 1" in md
    assert "## Per persona" in md
