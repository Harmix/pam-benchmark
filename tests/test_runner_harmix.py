"""Harmix runner aggregation/qa-response shaping (pure functions, no live judge)."""

from __future__ import annotations

from evals.base import JudgeResult
from runner import _aggregate_harmix, _qa_responses_harmix
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


def _verdict(correct: bool) -> JudgeResult:
    return JudgeResult(
        correct=correct, score=1.0 if correct else 0.0, confidence=0.9, reasoning="r"
    )


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
