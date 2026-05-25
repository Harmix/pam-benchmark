"""Prompt construction for the LoCoMo task.

Ported from the legacy `src/tasks/locomo/environment/task_eval/gpt_utils.py`
(now removed). The prompts intentionally match the LoCoMo paper format so F1
scores are comparable to published numbers.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import tiktoken

from datasets.locomo.schemas import LoCoMoQA, LoCoMoSample

# Per-model context window. Used to truncate the conversation when it exceeds
# the prompt budget. Falls back to a conservative 16k if a model isn't listed.
MODEL_CONTEXT_WINDOW: dict[str, int] = {
    "gpt-4-turbo": 128_000,
    "gpt-4-turbo-2024-04-09": 128_000,
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4": 8_192,
    "gpt-3.5-turbo-16k": 16_000,
    "gpt-3.5-turbo": 16_000,
}
DEFAULT_CONTEXT_WINDOW = 16_000

# Tokens reserved for the model's answer in the budget calculation.
ANSWER_TOKEN_BUDGET = 64

CONV_START_PROMPT = (
    "Below is a conversation between two people: {speaker_a} and {speaker_b}. "
    "The conversation takes place over multiple days and the date of each "
    "conversation is written at the beginning of the conversation.\n\n"
)

QA_PROMPT = (
    "\n\nBased on the above context, write an answer in the form of a short "
    "phrase for the following question. Answer with exact words from the "
    "context whenever possible.\n\n"
    "Question: {question} Short answer:"
)

QA_PROMPT_CAT_5 = (
    "\n\nBased on the above context, answer the following question.\n\n"
    "Question: {question} Short answer:"
)


@dataclass
class BuiltPrompt:
    """The prompt sent to the baseline plus per-question scoring metadata."""

    prompt: str
    expected_answer: str
    is_adversarial: bool = False
    # For category-5 the prompt presents two options. We must record which
    # letter corresponds to the correct option so the scorer can resolve a
    # one-letter ("a"/"b") model response back to text.
    cat5_answer_key: dict[str, str] | None = None


def _get_encoder(model: str) -> tiktoken.Encoding:
    """Best-effort tiktoken encoder for the given model name."""
    try:
        return tiktoken.encoding_for_model(model)
    except (KeyError, ValueError):
        return tiktoken.get_encoding("cl100k_base")


def _format_turn(turn_speaker: str, text: str, blip_caption: str | None) -> str:
    line = f'{turn_speaker} said, "{text}"\n'
    if blip_caption:
        line += f" and shared {blip_caption}.\n"
    return line


def build_conversation_context(
    sample: LoCoMoSample,
    *,
    model: str,
    num_question_tokens: int,
) -> str:
    """Render as much of the conversation as fits in the prompt budget.

    Mirrors the legacy implementation: walks sessions newest-first, packing
    turns in reverse order within each session until the token budget is
    exhausted. The oldest sessions are dropped first.
    """
    encoder = _get_encoder(model)
    window = MODEL_CONTEXT_WINDOW.get(model, DEFAULT_CONTEXT_WINDOW)
    budget = window - num_question_tokens - ANSWER_TOKEN_BUDGET

    speakers = sample.speakers()
    start_prompt = CONV_START_PROMPT.format(speaker_a=speakers[0], speaker_b=speakers[1])
    start_tokens = len(encoder.encode(start_prompt))
    budget -= start_tokens

    query_conv = ""
    stop = False
    for i in sample.session_indices():
        if stop:
            break
        date_time = sample.session_date_time(i)
        turns = sample.session(i)
        session_buf = ""
        for turn in reversed(turns):
            piece = _format_turn(turn.speaker, turn.text, turn.blip_caption)
            header = f"DATE: {date_time}\nCONVERSATION:\n"
            tentative = header + piece + session_buf + query_conv
            if len(encoder.encode(tentative)) <= budget:
                session_buf = piece + session_buf
            else:
                stop = True
                break
        if session_buf:
            query_conv = f"DATE: {date_time}\nCONVERSATION:\n{session_buf}\n\n" + query_conv

    return start_prompt + query_conv


def build_prompt(
    sample: LoCoMoSample,
    qa: LoCoMoQA,
    *,
    model: str,
    seed: int = 42,
) -> BuiltPrompt:
    """Build the single-question prompt for one LoCoMo QA record.

    Category-2 (temporal) prompts add a date-reasoning hint. Category-5
    (adversarial) prompts present a two-option multiple choice with random
    ordering — seeded for reproducibility across runs with the same `--seed`.
    """
    encoder = _get_encoder(model)

    if qa.category == 2:
        question_text = (
            qa.question + " Use DATE of CONVERSATION to answer with an approximate date."
        )
        expected = qa.answer or ""
        is_adv = False
        answer_key: dict[str, str] | None = None
        question_block = QA_PROMPT.format(question=question_text)

    elif qa.category == 5:
        correct = qa.answer if qa.answer is not None else "Not mentioned in the conversation"
        incorrect = (
            qa.adversarial_answer
            if qa.adversarial_answer is not None
            else "Not mentioned in the conversation"
        )
        # Deterministic per-question order so two runs with the same seed
        # see identical (a)/(b) assignments.
        rng = random.Random(f"{seed}|{sample.sample_id}|{qa.question}")
        if rng.random() < 0.5:
            opt_a, opt_b = incorrect, correct
            answer_key = {"a": incorrect, "b": correct}
        else:
            opt_a, opt_b = correct, incorrect
            answer_key = {"a": correct, "b": incorrect}
        question_text = f"{qa.question} Select the correct answer: (a) {opt_a} (b) {opt_b}."
        expected = correct
        is_adv = True
        question_block = QA_PROMPT_CAT_5.format(question=question_text)

    else:
        question_text = qa.question
        expected = qa.answer if qa.answer is not None else ""
        is_adv = False
        answer_key = None
        question_block = QA_PROMPT.format(question=question_text)

    num_question_tokens = len(encoder.encode(question_block))
    context = build_conversation_context(
        sample, model=model, num_question_tokens=num_question_tokens
    )
    full_prompt = context + question_block

    return BuiltPrompt(
        prompt=full_prompt,
        expected_answer=expected,
        is_adversarial=is_adv,
        cat5_answer_key=answer_key,
    )


def build_bare_prompt(
    qa: LoCoMoQA,
    *,
    sample: LoCoMoSample,
    seed: int = 42,
) -> BuiltPrompt:
    """Like `build_prompt`, but skips the conversation context.

    Used by external-memory baselines (e.g. Pam): the baseline already has the
    conversation in memory, so we only need the question text — but we still
    reuse the cat-2 (temporal) and cat-5 (adversarial MC) shaping so scoring
    behaves identically to the LiteLLM path. The cat-5 (a)/(b) randomization
    stays seeded against the same key so two runs with the same seed see the
    same ordering across baselines.
    """
    if qa.category == 2:
        question_text = (
            qa.question + " Use DATE of CONVERSATION to answer with an approximate date."
        )
        return BuiltPrompt(
            prompt=question_text,
            expected_answer=qa.answer or "",
            is_adversarial=False,
            cat5_answer_key=None,
        )

    if qa.category == 5:
        correct = qa.answer if qa.answer is not None else "Not mentioned in the conversation"
        incorrect = (
            qa.adversarial_answer
            if qa.adversarial_answer is not None
            else "Not mentioned in the conversation"
        )
        rng = random.Random(f"{seed}|{sample.sample_id}|{qa.question}")
        if rng.random() < 0.5:
            opt_a, opt_b = incorrect, correct
            answer_key = {"a": incorrect, "b": correct}
        else:
            opt_a, opt_b = correct, incorrect
            answer_key = {"a": correct, "b": incorrect}
        question_text = f"{qa.question} Select the correct answer: (a) {opt_a} (b) {opt_b}."
        return BuiltPrompt(
            prompt=question_text,
            expected_answer=correct,
            is_adversarial=True,
            cat5_answer_key=answer_key,
        )

    return BuiltPrompt(
        prompt=qa.question,
        expected_answer=qa.answer if qa.answer is not None else "",
        is_adversarial=False,
        cat5_answer_key=None,
    )


def resolve_cat5_answer(model_text: str, answer_key: dict[str, str]) -> str:
    """Translate a one-letter model reply ("a"/"(a)"/"b"/...) into its text."""
    s = model_text.strip().lower()
    if len(s) == 1:
        return answer_key.get(s, model_text)
    if "(a)" in s:
        return answer_key.get("a", model_text)
    if "(b)" in s:
        return answer_key.get("b", model_text)
    return model_text
