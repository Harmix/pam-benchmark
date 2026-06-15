"""Render a LoCoMo sample's conversation as a plain-text transcript.

The harness ingests this transcript into memory. It contains the conversation
ONLY (never the questions) so the resulting memory is query-agnostic — a
requirement for the baseline to be fair (see the system card).
"""

from __future__ import annotations

from datasets.locomo.schemas import LoCoMoSample


def conversation_to_transcript(sample: LoCoMoSample) -> str:
    """Sessions in original order, each with its date and speaker-tagged turns."""
    conv = sample.conversation
    speaker_a = conv.get("speaker_a", "Speaker A")
    speaker_b = conv.get("speaker_b", "Speaker B")

    lines: list[str] = [f"Conversation between {speaker_a} and {speaker_b}.", ""]

    # session_<i> keys in numeric order; each has an optional session_<i>_date_time.
    session_keys = sorted(
        (k for k in conv if k.startswith("session_") and not k.endswith("_date_time")),
        key=lambda k: int(k.split("_")[1]) if k.split("_")[1].isdigit() else 0,
    )
    for key in session_keys:
        turns = conv.get(key) or []
        if not isinstance(turns, list):
            continue
        idx = key.split("_")[1]
        date = conv.get(f"{key}_date_time", "")
        header = f"## Session {idx}" + (f" — {date}" if date else "")
        lines.append(header)
        for turn in turns:
            if not isinstance(turn, dict):
                continue
            speaker = turn.get("speaker", "")
            text = turn.get("text", "")
            if text:
                lines.append(f"{speaker}: {text}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"
