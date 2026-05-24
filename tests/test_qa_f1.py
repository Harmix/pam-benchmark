"""Tests for LoCoMo-style token F1 scoring."""

from __future__ import annotations

import pytest

from evals.qa_f1 import score_locomo_qa


@pytest.mark.parametrize(
    "category, prediction, ground_truth, expected_min",
    [
        # cat 1: multi-answer single-hop, exact match
        (1, "Adoption agencies", "Adoption agencies", 1.0),
        # cat 2: temporal, exact match
        (2, "7 May 2023", "7 May 2023", 1.0),
        # cat 3: open-domain — semicolons split; first form is canonical
        (3, "Psychology, counseling certification", "Psychology, counseling certification; psych cert", 1.0),
        # cat 4: multi-hop exact
        (4, "mental health", "mental health", 1.0),
    ],
)
def test_perfect_match_per_category(category, prediction, ground_truth, expected_min):
    score = score_locomo_qa(prediction=prediction, ground_truth=ground_truth, category=category)
    assert score >= expected_min - 1e-9


def test_partial_match_gives_partial_credit():
    score = score_locomo_qa(
        prediction="adoption", ground_truth="adoption agencies", category=4
    )
    assert 0.0 < score < 1.0


def test_completely_wrong_is_zero():
    assert score_locomo_qa(prediction="paris", ground_truth="berlin", category=4) == 0.0


def test_cat5_correctly_refuses():
    # adversarial: refusal language counts as correct
    for refusal in [
        "No information available in the conversation.",
        "Not mentioned in the conversation.",
        "NOT MENTIONED anywhere",
    ]:
        assert (
            score_locomo_qa(prediction=refusal, ground_truth="ignored", category=5) == 1.0
        )


def test_cat5_takes_the_bait_is_zero():
    # adversarial: answering the false premise scores 0
    assert (
        score_locomo_qa(prediction="self-care is important", ground_truth="ignored", category=5)
        == 0.0
    )


def test_normalization_handles_articles_and_punctuation():
    # The article "the" and the comma should be stripped during normalization.
    a = score_locomo_qa(prediction="the cat", ground_truth="cat", category=4)
    b = score_locomo_qa(prediction="cat,", ground_truth="cat", category=4)
    assert a == 1.0
    assert b == 1.0


def test_unknown_category_raises():
    with pytest.raises(ValueError):
        score_locomo_qa(prediction="x", ground_truth="y", category=99)


def test_empty_prediction_is_zero_except_cat5():
    assert score_locomo_qa(prediction="", ground_truth="cat", category=4) == 0.0
    # cat 5 with empty doesn't contain "not mentioned" → 0
    assert score_locomo_qa(prediction="", ground_truth="ignored", category=5) == 0.0
