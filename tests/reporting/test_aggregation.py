"""Report aggregation — pure functions consumed by both HTML and Markdown."""

from __future__ import annotations

import pytest

from reporting.html import (
    _accuracy_class,
    _aggregate_headline,
    _avg_context_tokens,
    _avg_input_tokens,
    _incorrect,
    _incorrect_categories,
    _per_category,
    _per_sample,
    _per_sample_tokens,
    build_context,
)
from reporting.markdown import render_markdown


def _doc(
    sample_id: str = "s1",
    seed: int = 42,
    baseline: str = "gpt-4-turbo",
    qa: list[dict] | None = None,
) -> dict:
    qa = qa or []
    f1_sum = sum(q["f1_score"] for q in qa)
    judge_correct = sum(1 for q in qa if q["judge_correct"])
    return {
        "exp_name": "t",
        "sample_id": sample_id,
        "seed": seed,
        "baseline": baseline,
        "judge_model": "gpt-4o",
        "dataset_name": "locomo@1.0",
        "task_name": "locomo",
        "total_questions": len(qa),
        "correct_count": sum(1 for q in qa if q["f1_score"] >= 0.5),
        "incorrect_count": sum(1 for q in qa if q["f1_score"] < 0.5),
        "overall_accuracy": f1_sum / len(qa) if qa else 0.0,
        "total_f1_sum": f1_sum,
        "judge_accuracy": judge_correct / len(qa) if qa else 0.0,
        "judge_correct_count": judge_correct,
        "total_input_tokens": sum(q["input_tokens"] for q in qa),
        "total_output_tokens": sum(q["output_tokens"] for q in qa),
        "total_cost_usd": sum(q["est_cost_usd"] for q in qa),
        "avg_latency_ms": sum(q["latency_ms"] for q in qa) / len(qa) if qa else 0.0,
        "p50_latency_ms": 0.0,
        "p95_latency_ms": 0.0,
        "execution_time_seconds": 1.0,
        "qa_responses": qa,
    }


def _qa(
    q_num: int = 1,
    category_name: str = "single_hop",
    f1: float = 1.0,
    judge_correct: bool = True,
):
    return {
        "question_num": q_num,
        "question": f"Q{q_num}",
        "expected_answer": "x",
        "model_answer": "x" if judge_correct else "y",
        "category": 1 if category_name == "single_hop" else 4,
        "category_name": category_name,
        "evidence": ["D1:1"],
        "is_adversarial": False,
        "f1_score": f1,
        "judge_correct": judge_correct,
        "judge_score": 1.0 if judge_correct else 0.0,
        "judge_confidence": 0.9,
        "judge_reasoning": "r",
        "input_tokens": 1000,
        "output_tokens": 10,
        "est_cost_usd": 0.01,
        "latency_ms": 1500.0,
    }


@pytest.mark.parametrize(
    "pct, expected_class",
    [(95.0, "good"), (80.0, "good"), (79.99, "warn"), (50.0, "warn"), (49.99, "bad"), (0.0, "bad")],
)
def test_accuracy_class_boundaries(pct, expected_class):
    assert _accuracy_class(pct) == expected_class


def test_headline_empty():
    out = _aggregate_headline([])
    assert out["total_questions"] == 0
    assert out["judge_accuracy_pct"] == 0.0


def test_headline_combines_across_docs():
    docs = [
        _doc(qa=[_qa(1, f1=1.0, judge_correct=True), _qa(2, f1=0.0, judge_correct=False)]),
        _doc(sample_id="s2", qa=[_qa(1, f1=1.0, judge_correct=True)]),
    ]
    h = _aggregate_headline(docs)
    assert h["total_questions"] == 3
    assert h["judge_correct"] == 2
    assert h["judge_accuracy_pct"] == pytest.approx(round(2 / 3 * 100, 1))
    # Cost is intentionally absent from the report headline.
    assert "total_cost_usd" not in h


def test_per_category_groups_canonical_order():
    docs = [
        _doc(
            qa=[
                _qa(1, category_name="multi_hop", f1=1.0, judge_correct=True),
                _qa(2, category_name="single_hop", f1=1.0, judge_correct=True),
                _qa(3, category_name="single_hop", f1=0.0, judge_correct=False),
            ]
        )
    ]
    rows = _per_category(docs)
    names = [r["name"] for r in rows]
    assert names == ["Single Hop", "Multi Hop"]
    single = next(r for r in rows if r["name"] == "Single Hop")
    assert single["count"] == 2
    assert single["judge_correct"] == 1
    assert single["judge_pct"] == 50.0


def test_per_sample_one_row_per_doc():
    docs = [_doc(sample_id=f"s{i}", qa=[_qa(1)]) for i in range(3)]
    rows = _per_sample(docs)
    assert len(rows) == 3
    assert {r["sample_id"] for r in rows} == {"s0", "s1", "s2"}
    assert all("judge_class" in r for r in rows)
    # Seed column dropped; Avg. Context Tokens + memory-creation added.
    # Batch size lives at the report top, not per-sample.
    assert all("seed" not in r for r in rows)
    assert all("batch_size" not in r for r in rows)
    assert all("avg_context_tokens" in r for r in rows)
    assert all("memory_creation_duration_sec" in r for r in rows)


def test_build_context_batch_sizes_at_top():
    docs = [
        {"baseline": "memory_md_mcp", "sample_id": "a", "batch_size": 10},
        {"baseline": "pam", "sample_id": "b", "pam_batch_size": 5},
        {"baseline": "gpt-4o", "sample_id": "c"},  # single-call → 1
    ]
    ctx = build_context(dataset="locomo", exp_name="x", docs=docs)
    assert ctx["batch_sizes"] == [1, 5, 10]


def test_avg_context_tokens_non_pam_uses_context_total():
    doc = {"baseline": "gpt-4-turbo", "total_questions": 4, "total_context_tokens": 80}
    assert _avg_context_tokens(doc) == pytest.approx(20.0)


def test_avg_context_tokens_pam_uses_enriched_minus_prompt():
    # Pam: (enriched - prompt) / questions
    doc = {
        "baseline": "pam",
        "total_questions": 5,
        "total_context_tokens": 0,
        "total_enriched_user_prompt_tokens": 500,
        "total_prompt_tokens": 100,
    }
    assert _avg_context_tokens(doc) == pytest.approx(80.0)


def test_avg_context_tokens_zero_questions_safe():
    assert _avg_context_tokens({"baseline": "pam", "total_questions": 0}) == 0.0


def test_avg_input_tokens_non_pam_uses_input_total():
    doc = {"baseline": "gpt-4-turbo", "total_questions": 4, "total_input_tokens": 400}
    assert _avg_input_tokens(doc) == pytest.approx(100.0)


def test_avg_input_tokens_pam_uses_enriched():
    doc = {
        "baseline": "pam",
        "total_questions": 5,
        "total_input_tokens": 0,
        "total_enriched_user_prompt_tokens": 500,
    }
    assert _avg_input_tokens(doc) == pytest.approx(100.0)


def test_per_sample_tokens_columns_and_values():
    doc = {
        "baseline": "pam",
        "sample_id": "s1",
        "total_questions": 2,
        "total_input_tokens": 0,
        "total_output_tokens": 40,
        "total_context_tokens": 0,
        "total_prompt_tokens": 60,
        "total_enriched_user_prompt_tokens": 200,
        "total_agent_input_tokens": 100,
        "total_agent_output_tokens": 20,
        "total_agent_cache_read_tokens": 8,
        "total_agent_cache_write_tokens": 4,
    }
    row = _per_sample_tokens([doc])[0]
    assert row["avg_input"] == pytest.approx(100.0)  # enriched 200 / 2
    assert row["avg_output"] == pytest.approx(20.0)
    assert row["avg_context"] == pytest.approx(70.0)  # (200 - 60) / 2
    assert row["avg_prompt"] == pytest.approx(30.0)
    assert row["avg_agent_input"] == pytest.approx(50.0)
    assert row["avg_agent_output"] == pytest.approx(10.0)
    assert row["avg_agent_cache_read"] == pytest.approx(4.0)
    assert row["avg_agent_cache_write"] == pytest.approx(2.0)


def test_per_sample_tokens_zero_questions_safe():
    row = _per_sample_tokens([{"baseline": "gpt-4-turbo", "sample_id": "s", "total_questions": 0}])[
        0
    ]
    assert row["avg_input"] == 0.0
    assert row["avg_agent_cache_write"] == 0.0


def test_incorrect_categories_counts_and_canonical_order():
    incorrect = [
        {"category_name": "adversarial"},
        {"category_name": "single_hop"},
        {"category_name": "single_hop"},
        {"category_name": "temporal"},
    ]
    cats = _incorrect_categories(incorrect)
    # Canonical order: single_hop, temporal, ..., adversarial last.
    assert [c["name"] for c in cats] == ["single_hop", "temporal", "adversarial"]
    assert {c["name"]: c["count"] for c in cats} == {
        "single_hop": 2,
        "temporal": 1,
        "adversarial": 1,
    }


def test_incorrect_filters_to_judge_incorrect_only():
    docs = [
        _doc(
            sample_id="s1",
            qa=[
                _qa(1, judge_correct=True),
                _qa(2, judge_correct=False),
                _qa(3, judge_correct=False),
            ],
        )
    ]
    rows = _incorrect(docs)
    assert len(rows) == 2
    assert all(not r["judge_correct"] for r in rows)
    # sample_id propagated to each row
    assert all(r["sample_id"] == "s1" for r in rows)


def test_build_context_collects_distinct_baselines_seeds():
    docs = [
        _doc(baseline="gpt-4-turbo", seed=42, qa=[_qa(1)]),
        _doc(baseline="gpt-4-turbo", seed=1337, qa=[_qa(1)]),
        _doc(baseline="claude-3-5-sonnet", seed=42, qa=[_qa(1)]),
    ]
    ctx = build_context(dataset="locomo", exp_name="x", docs=docs)
    assert ctx["baselines"] == ["claude-3-5-sonnet", "gpt-4-turbo"]
    assert ctx["seeds"] == [42, 1337]
    assert ctx["sample_count"] == 1  # all the same sample_id "s1"


def test_markdown_renders_without_errors():
    docs = [_doc(qa=[_qa(1, judge_correct=True), _qa(2, judge_correct=False)])]
    md = render_markdown(dataset="locomo", exp_name="x", docs=docs)
    assert "# Locomo report — x" in md
    assert "LLM-judge" in md
    assert "Per category" in md
    assert "Per sample" in md
