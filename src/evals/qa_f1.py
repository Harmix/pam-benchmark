"""Token-level F1 — ported from the legacy task_eval/evaluation.py.

Same normalization (punctuation strip, article removal, Porter stemming) and
the same category-specific dispatch as the LoCoMo paper, so numbers stay
comparable. Only the harness around it has changed.
"""

from __future__ import annotations

import string
from collections import Counter

import numpy as np
import regex
from nltk.stem import PorterStemmer

_STEMMER = PorterStemmer()


def _normalize_answer(s: str) -> str:
    s = s.replace(",", "")

    def remove_articles(text: str) -> str:
        return regex.sub(r"\b(a|an|the|and)\b", " ", text)

    def white_space_fix(text: str) -> str:
        return " ".join(text.split())

    def remove_punc(text: str) -> str:
        exclude = set(string.punctuation)
        return "".join(ch for ch in text if ch not in exclude)

    def lower(text: str) -> str:
        return text.lower()

    return white_space_fix(remove_articles(remove_punc(lower(s))))


def _f1_pair(prediction: str, ground_truth: str) -> float:
    pred_tokens = [_STEMMER.stem(w) for w in _normalize_answer(prediction).split()]
    truth_tokens = [_STEMMER.stem(w) for w in _normalize_answer(ground_truth).split()]
    if not pred_tokens or not truth_tokens:
        return 0.0
    common = Counter(pred_tokens) & Counter(truth_tokens)
    num_same = sum(common.values())
    if num_same == 0:
        return 0.0
    precision = num_same / len(pred_tokens)
    recall = num_same / len(truth_tokens)
    return (2 * precision * recall) / (precision + recall)


def _f1_multi(prediction: str, ground_truth: str) -> float:
    """Multi-answer F1: comma-split both sides, take max over predictions
    per ground-truth, then average across ground truths.
    """
    preds = [p.strip() for p in prediction.split(",")]
    truths = [g.strip() for g in ground_truth.split(",")]
    return float(np.mean([max(_f1_pair(p, g) for p in preds) for g in truths]))


def score_locomo_qa(
    *,
    prediction: str,
    ground_truth: str,
    category: int,
) -> float:
    """LoCoMo-style F1 for one (prediction, ground_truth, category) triple.

    Dispatch matches the legacy implementation:
        cat 1 (single_hop, multi-answer)   -> _f1_multi
        cat 2, 3, 4                        -> _f1_pair
        cat 5 (adversarial)                -> 1.0 if model declines to answer
    """
    pred = prediction or ""
    truth = ground_truth or ""
    if category == 3:
        # category 3 ground truth may have ";"-separated forms; LoCoMo paper
        # takes the first as canonical.
        truth = truth.split(";")[0].strip()
    if category == 5:
        text = pred.lower()
        if "no information available" in text or "not mentioned" in text:
            return 1.0
        return 0.0
    if category == 1:
        return _f1_multi(pred, truth)
    if category in (2, 3, 4):
        return _f1_pair(pred, truth)
    raise ValueError(f"Unknown LoCoMo category: {category}")
