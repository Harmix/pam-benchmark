"""Numbered Q/A batch protocol shared by every "external memory" baseline.

A batch of questions is rendered as a strict ``Q1..QN`` prompt asking for an
``A1..AN`` reply; the reply is parsed back into per-question answers. The same
helpers serve Pam (over SSE) and the MCP-on-harness baselines (over Claude
Code), so the rendering/parsing/retry-distribution logic lives in exactly one
place.
"""

from __future__ import annotations

import re

import litellm


def count_tokens(model: str | None, text: str) -> int:
    """Token count of `text` per the model's tokenizer (0 if no model is set or
    counting fails). Used for both the prompt and the answer."""
    if not text or not model:
        return 0
    try:
        return int(litellm.token_counter(model=model, text=text))
    except Exception:
        return 0


def distribute(total: int, n: int) -> list[int]:
    """Split a per-batch integer total into `n` per-question shares that sum
    back to `total` exactly (remainder spread over the first questions)."""
    if n <= 0:
        return []
    base, rem = divmod(int(total or 0), n)
    return [base + (1 if i < rem else 0) for i in range(n)]


_ANSWER_LINE_RE = re.compile(r"^\s*A(\d+)\s*[:\.\)]\s*(.*)$", re.IGNORECASE)
# Fallback for a line where the model dropped the "A" prefix (e.g. "9: Camping"
# instead of "A9: Camping"). Only honored when the bare number is the next
# sequential slot (see parse_batch_response) so numbered lists *inside* an
# answer aren't mistaken for new answers.
_BARE_NUM_LINE_RE = re.compile(r"^\s*(\d+)\s*[:\.\)]\s*(.*)$")

# Reasoning models sometimes wrap the reply in <think>...</think> and/or a
# <final>...</final> block. A stream can even begin mid-thought (the opening
# <think> already gone), so the reasoning text gets glued onto the same line as
# the first answer, e.g.
#   ...output it exactly as requested.</think><final>A1: Progressive/liberal
# which leaves `A1:` off the line start and drops slot 1. Cutting everything up
# to the last such boundary tag restores a clean `A1:`-first answer block.
_SCAFFOLD_BOUNDARIES = ("</think>", "<final>")


def strip_reasoning_scaffold(text: str) -> str:
    cut = 0
    for marker in _SCAFFOLD_BOUNDARIES:
        idx = text.rfind(marker)
        if idx != -1:
            cut = max(cut, idx + len(marker))
    if cut:
        text = text[cut:]
    return text.replace("</final>", "").strip()


def render_batch_prompt(prompts: list[str]) -> str:
    """Render a numbered Q1..QN prompt asking for A1..AN-formatted answers.

    The format rules are deliberately strict: the system under test is a
    tool-using agent that sometimes streams status narration, wraps its reply in
    reasoning tags, or drops the "A" prefix on a line. The instructions push it
    toward a clean, complete answer block so every slot parses; the parser is
    tolerant of the rest.
    """
    questions_block = "\n".join(f"Q{i}: {p}" for i, p in enumerate(prompts, start=1))
    template_block = "\n".join(f"A{i}: <short answer>" for i in range(1, len(prompts) + 1))
    n = len(prompts)
    return (
        "Answer each of the following questions about the conversation in memory.\n"
        "Reply in the EXACT format below: one answer per line, each line starting "
        'with a capital "A" followed by the question number and a colon. Keep each '
        "answer concise.\n\n"
        "Rules:\n"
        f"- Output ONLY the {n} answer lines (A1..A{n}). No preamble, no status "
        "updates, no reasoning, no thinking tags, no closing remarks.\n"
        '- Begin every line with "A" and the matching number (A1, A2, ...). Never '
        'drop the "A" and never merge two answers onto one line.\n'
        "- Provide an answer for every question. If you are unsure, give your best "
        "guess from memory; never leave a line blank.\n\n"
        f"{template_block}\n\n"
        f"{questions_block}"
    )


def parse_batch_response(text: str, n_expected: int) -> list[str]:
    """Extract `n_expected` answers from a numbered-reply response.

    Lines that start with `A<i>:` (or `A<i>.` / `A<i>)`) are captured and
    associated with question `i`. Continuation lines (no `Ai:` prefix) are
    appended to the most recently captured answer. Missing slots get empty
    strings — the caller logs a warning so the F1/judge pipeline still sees
    something for each question.

    A leading <think>/<final> reasoning scaffold (which can land glued onto the
    first answer line) is stripped first — see `strip_reasoning_scaffold`. A
    line that drops the "A" prefix ("9:" instead of "A9:") is recovered when its
    number is the next expected slot.
    """
    text = strip_reasoning_scaffold(text)
    answers: dict[int, list[str]] = {}
    current_idx: int | None = None

    for raw_line in text.splitlines():
        m = _ANSWER_LINE_RE.match(raw_line)
        if m:
            current_idx = int(m.group(1))
            answers.setdefault(current_idx, []).append(m.group(2).strip())
            continue

        bare = _BARE_NUM_LINE_RE.match(raw_line)
        if bare:
            idx = int(bare.group(1))
            # Accept a missing-"A" line only if it's the next slot we expect and
            # we haven't already captured it — keeps numbered lists inside an
            # answer from masquerading as new answers.
            if idx == (current_idx or 0) + 1 and 1 <= idx <= n_expected and idx not in answers:
                current_idx = idx
                answers.setdefault(idx, []).append(bare.group(2).strip())
                continue

        if current_idx is not None and raw_line.strip():
            answers[current_idx].append(raw_line.strip())

    out: list[str] = []
    for i in range(1, n_expected + 1):
        parts = answers.get(i, [])
        joined = " ".join(p for p in parts if p).strip()
        out.append(joined)
    return out
