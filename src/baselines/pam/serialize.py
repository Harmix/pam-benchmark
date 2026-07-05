"""Serialize a LoCoMo sample into the file payload Pam ingests.

One readable transcript (`.txt`) per conversation. Pam's memory pipeline runs
the *generic* (document) extractor over uploaded files: given raw JSON it
summarizes the data structure instead of enumerating facts (observed: a 419-turn
conversation dumped as JSON yields 0 facts), whereas given natural prose it mines
facts the same way it does for email bodies. So we render the conversation as
speaker-labeled dialogue, grouped by session with its date, preserving the
original session order. Pam builds one memory per uploaded sample.
"""

from __future__ import annotations

from datasets.locomo.schemas import LoCoMoSample


def _render_turn(turn: dict) -> str | None:
    """Render one turn as ``<speaker>: <text>``.

    Image turns carry no ``text`` but a ``blip_caption``; fold the caption in so
    facts that depend on a shared photo survive. Returns None for empty turns.
    """
    speaker = (turn.get("speaker") or "").strip() or "Unknown"
    text = (turn.get("text") or "").strip()
    caption = (turn.get("blip_caption") or "").strip()
    parts: list[str] = []
    if text:
        parts.append(text)
    if caption:
        parts.append(f"[shared a photo: {caption}]")
    if not parts:
        return None
    return f"{speaker}: {' '.join(parts)}"


def serialize_sample(sample: LoCoMoSample) -> list[tuple[str, bytes]]:
    """Return ``[(filename, utf8_bytes)]`` ready for ``process_generic_files``.

    Renders the conversation as a readable transcript: a one-line header naming
    the speakers, then each ``session_<i>`` as ``=== Session <i> — <date_time> ===``
    followed by ``<speaker>: <text>`` lines. Sessions keep their original order.
    """
    conv = sample.conversation
    speaker_a = conv.get("speaker_a")
    speaker_b = conv.get("speaker_b")

    lines: list[str] = []
    if speaker_a is not None and speaker_b is not None:
        lines.append(f"Conversation between {speaker_a} and {speaker_b}.")

    for key, value in conv.items():
        if not key.startswith("session_") or key.endswith("_date_time"):
            continue
        if not isinstance(value, list):
            continue
        session_no = key[len("session_") :]
        date_time = conv.get(f"{key}_date_time", "")
        header = f"=== Session {session_no}"
        if date_time:
            header += f" — {date_time}"
        header += " ==="
        lines.append("")
        lines.append(header)
        for turn in value:
            rendered = _render_turn(turn)
            if rendered is not None:
                lines.append(rendered)

    body = ("\n".join(lines).strip() + "\n").encode("utf-8")
    filename = f"{sample.sample_id}_conversation.txt"
    return [(filename, body)]
