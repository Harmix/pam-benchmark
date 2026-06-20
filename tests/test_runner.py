"""Runner aggregation helpers — dataset-agnostic and shared by every Mongo write."""

from __future__ import annotations

import pytest

from runner import _aggregate, _qa_responses


def _scores(predictions, judges):
    """Synthetic F1 derived from the judge for these tests."""
    return [1.0 if j.correct else 0.0 for j in judges]


def test_aggregate_empty_safe():
    out = _aggregate([], [], [])
    assert out["total_questions"] == 0
    assert out["correct_count"] == 0
    assert out["overall_accuracy"] == 0.0
    assert out["judge_accuracy"] == 0.0


def test_aggregate_counts_correct_threshold(prediction_factory, judge_factory):
    # F1 ≥ 0.5 = correct; build a deterministic mix
    preds = [prediction_factory(question_num=i) for i in range(1, 5)]
    judges = [
        judge_factory(correct=True),
        judge_factory(correct=False),
        judge_factory(correct=True),
        judge_factory(correct=False),
    ]
    f1 = [0.9, 0.49, 0.5, 0.0]
    out = _aggregate(preds, f1, judges)
    assert out["total_questions"] == 4
    assert out["correct_count"] == 2  # 0.9, 0.5
    assert out["incorrect_count"] == 2
    assert out["judge_correct_count"] == 2
    assert out["judge_accuracy"] == pytest.approx(0.5)
    assert out["overall_accuracy"] == pytest.approx(sum(f1) / 4, abs=1e-4)


def test_aggregate_per_category_breakdown(prediction_factory, judge_factory):
    preds = [
        prediction_factory(question_num=1, category=1, category_name="single_hop"),
        prediction_factory(question_num=2, category=1, category_name="single_hop"),
        prediction_factory(question_num=3, category=2, category_name="temporal"),
    ]
    judges = [
        judge_factory(correct=True),
        judge_factory(correct=False),
        judge_factory(correct=True),
    ]
    f1 = [1.0, 0.0, 0.6]
    out = _aggregate(preds, f1, judges)
    assert out["category_single_hop_count"] == 2
    assert out["category_single_hop_accuracy"] == pytest.approx(0.5)
    assert out["category_single_hop_llm_judge_total"] == 2
    assert out["category_single_hop_llm_judge_accuracy"] == pytest.approx(0.5)
    assert out["category_temporal_count"] == 1
    assert out["category_temporal_accuracy"] == pytest.approx(0.6)


def test_aggregate_sums_costs_and_tokens(prediction_factory, judge_factory):
    preds = [
        prediction_factory(question_num=1, input_tokens=100, output_tokens=10, est_cost_usd=0.05),
        prediction_factory(question_num=2, input_tokens=200, output_tokens=20, est_cost_usd=0.15),
    ]
    judges = [judge_factory(), judge_factory()]
    out = _aggregate(preds, [1.0, 1.0], judges)
    assert out["total_input_tokens"] == 300
    assert out["total_output_tokens"] == 30
    assert out["total_cost_usd"] == pytest.approx(0.20)


def test_aggregate_sums_agent_tokens(prediction_factory, judge_factory):
    preds = [
        prediction_factory(
            question_num=1,
            agent_input_tokens=100,
            agent_output_tokens=10,
            agent_cache_read_tokens=5,
            agent_cache_write_tokens=2,
            enriched_user_prompt_tokens=40,
        ),
        prediction_factory(
            question_num=2,
            agent_input_tokens=200,
            agent_output_tokens=20,
            agent_cache_read_tokens=7,
            agent_cache_write_tokens=3,
            enriched_user_prompt_tokens=60,
        ),
    ]
    judges = [judge_factory(), judge_factory()]
    out = _aggregate(preds, [1.0, 1.0], judges)
    assert out["total_agent_input_tokens"] == 300
    assert out["total_agent_output_tokens"] == 30
    assert out["total_agent_cache_read_tokens"] == 12
    assert out["total_agent_cache_write_tokens"] == 5
    assert out["total_enriched_user_prompt_tokens"] == 100


def test_aggregate_enriched_none_when_all_none(prediction_factory, judge_factory):
    # claude-code-style baselines set enriched/injected to None → total stays None.
    preds = [
        prediction_factory(question_num=1, enriched_user_prompt_tokens=None),
        prediction_factory(question_num=2, enriched_user_prompt_tokens=None),
    ]
    out = _aggregate(preds, [1.0, 1.0], [judge_factory(), judge_factory()])
    assert out["total_enriched_user_prompt_tokens"] is None


def test_aggregate_enriched_sums_when_present(prediction_factory, judge_factory):
    preds = [
        prediction_factory(question_num=1, enriched_user_prompt_tokens=40),
        prediction_factory(question_num=2, enriched_user_prompt_tokens=60),
    ]
    out = _aggregate(preds, [1.0, 1.0], [judge_factory(), judge_factory()])
    assert out["total_enriched_user_prompt_tokens"] == 100


def test_qa_responses_carry_agent_tokens(prediction_factory, judge_factory):
    preds = [prediction_factory(question_num=1, agent_input_tokens=42)]
    rows = _qa_responses(preds, [1.0], [judge_factory()])
    assert rows[0]["agent_input_tokens"] == 42
    for key in (
        "agent_output_tokens",
        "agent_cache_read_tokens",
        "agent_cache_write_tokens",
        "enriched_user_prompt_tokens",
    ):
        assert key in rows[0]


def test_aggregate_latency_summary_present(prediction_factory, judge_factory):
    preds = [
        prediction_factory(question_num=1, latency_ms=100),
        prediction_factory(question_num=2, latency_ms=1900),
    ]
    judges = [judge_factory(), judge_factory()]
    out = _aggregate(preds, [1.0, 1.0], judges)
    assert "avg_latency_ms" in out
    assert "p50_latency_ms" in out
    assert "p95_latency_ms" in out
    assert out["avg_latency_ms"] == pytest.approx(1000.0)


def test_qa_responses_shape_matches_mongo_schema(prediction_factory, judge_factory):
    preds = [
        prediction_factory(question_num=1, category=1, category_name="single_hop"),
        prediction_factory(
            question_num=2, category=5, category_name="adversarial", is_adversarial=True
        ),
    ]
    judges = [
        judge_factory(correct=True),
        judge_factory(correct=False, score=0.0, reasoning="wrong"),
    ]
    rows = _qa_responses(preds, [1.0, 0.0], judges)
    assert len(rows) == 2
    # Schema parity with §9.1 of the rewrite plan
    required = {
        "question_num",
        "question",
        "expected_answer",
        "model_answer",
        "category",
        "category_name",
        "evidence",
        "is_adversarial",
        "f1_score",
        "judge_correct",
        "judge_score",
        "judge_confidence",
        "judge_reasoning",
        "input_tokens",
        "output_tokens",
        "est_cost_usd",
        "latency_ms",
    }
    assert required <= set(rows[0].keys())
    # Per-question fidelity
    assert rows[0]["judge_correct"] is True
    assert rows[1]["judge_correct"] is False
    assert rows[1]["is_adversarial"] is True


def test_qa_responses_preserves_order(prediction_factory, judge_factory):
    preds = [prediction_factory(question_num=i, question=f"q{i}") for i in range(1, 6)]
    judges = [judge_factory() for _ in preds]
    rows = _qa_responses(preds, [1.0] * 5, judges)
    assert [r["question_num"] for r in rows] == [1, 2, 3, 4, 5]
    assert [r["question"] for r in rows] == ["q1", "q2", "q3", "q4", "q5"]
