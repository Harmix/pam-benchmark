"""Harmix runner aggregation/qa-response shaping (pure functions, no live judge)."""

from __future__ import annotations

from evals.base import JudgeResult
from runner import _aggregate_harmix, _aggregate_samples, _qa_responses_harmix
from tasks.harmix.pipeline import HarmixPrediction


def _pred(num: int, expected: str | None, notes: str | None = None) -> HarmixPrediction:
    return HarmixPrediction(
        question_num=num,
        case_id=f"c-{num}",
        question=f"q-{num}",
        expected_answer=expected,
        grading_notes=notes,
        model_answer=f"a-{num}",
        input_tokens=10,
        output_tokens=5,
        est_cost_usd=0.01,
        latency_ms=100.0,
    )


def _verdict(correct: bool):
    """A single-sample aggregated verdict (the K=1 case)."""
    jr = JudgeResult(correct=correct, score=1.0 if correct else 0.0, confidence=0.9, reasoning="r")
    return _aggregate_samples(["a-x"], [jr])


def test_aggregate_excludes_null_expected_from_accuracy():
    preds = [_pred(1, "gold-1"), _pred(2, None), _pred(3, "gold-3")]
    # Only the two gold-bearing cases are judged (indices 0 and 2).
    verdicts = {0: _verdict(True), 2: _verdict(False)}
    agg = _aggregate_harmix(preds, verdicts)

    assert agg["total_questions"] == 3
    assert agg["judged_count"] == 2
    assert agg["unjudged_count"] == 1
    assert agg["judge_correct_count"] == 1
    assert agg["judge_accuracy"] == 0.5  # 1 / 2, null case excluded
    assert agg["total_input_tokens"] == 30
    assert agg["total_cost_usd"] == 0.03


def test_qa_responses_marks_unjudged_rows():
    preds = [_pred(1, "gold-1", notes="be strict"), _pred(2, None)]
    verdicts = {0: _verdict(True)}
    rows = _qa_responses_harmix(preds, verdicts)

    assert rows[0]["judged"] is True
    assert rows[0]["judge_correct"] is True
    assert rows[0]["grading_notes"] == "be strict"
    assert rows[1]["judged"] is False
    assert rows[1]["judge_correct"] is None
    assert rows[1]["judge_reasoning"] is None
    assert rows[1]["expected_answer"] is None


def _jr(correct: bool, score: float, conf: float = 0.9) -> JudgeResult:
    return JudgeResult(correct=correct, score=score, confidence=conf, reasoning="r")


def test_aggregate_samples_avg_at_k_and_representative():
    # 4 samples: scores 1.0/0.0/0.6/0.2, mean 0.45; 2 of 4 correct → frac 0.5.
    answers = ["A", "B", "C", "D"]
    verdicts = [_jr(True, 1.0), _jr(False, 0.0), _jr(True, 0.6), _jr(False, 0.2)]
    agg = _aggregate_samples(answers, verdicts)
    assert abs(agg.mean_score - 0.45) < 1e-9
    assert abs(agg.frac_correct - 0.5) < 1e-9  # avg@k for this question
    assert agg.n_samples == 4
    assert agg.score_std > 0
    # Representative = closest to the mean 0.45 → score 0.6 (Δ0.15) beats 0.2 (Δ0.25).
    assert agg.shown_answer == "C"


def test_aggregate_samples_ties_break_on_confidence():
    # Two samples equidistant from the mean (0.5): pick the more confident one.
    agg = _aggregate_samples(["lo", "hi"], [_jr(False, 0.0, conf=0.5), _jr(True, 1.0, conf=0.95)])
    assert abs(agg.mean_score - 0.5) < 1e-9
    assert agg.shown_answer == "hi"


def test_aggregate_harmix_avg_at_k_accuracy_and_std():
    preds = [_pred(1, "gold-1"), _pred(2, "gold-2")]
    # Q1: 2/4 correct (0.5); Q2: 4/4 correct (1.0) → avg@k = 0.75, std = 0.25.
    v1 = _aggregate_samples(
        ["a", "b", "c", "d"], [_jr(True, 1), _jr(False, 0), _jr(True, 1), _jr(False, 0)]
    )
    v2 = _aggregate_samples(["a", "b", "c", "d"], [_jr(True, 1)] * 4)
    agg = _aggregate_harmix(preds, {0: v1, 1: v2})
    assert agg["judge_accuracy"] == 0.75
    assert agg["judge_accuracy_std"] == 0.25
    assert agg["samples_per_question"] == 4
    assert agg["judge_correct_count"] == 1.5  # 0.5 + 1.0 expected correct
