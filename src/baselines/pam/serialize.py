"""Serialize a LoCoMo sample into the file payload Pam ingests.

One JSON file per conversation, preserving the original key order from
`src/datasets/locomo/data/locomo10.json`. Pam builds one memory per uploaded
sample.
"""

from __future__ import annotations

import json

from datasets.locomo.schemas import LoCoMoSample


def serialize_sample(sample: LoCoMoSample) -> list[tuple[str, bytes]]:
    """Return `[(filename, json_bytes)]` ready for `PamClient.upload_generic_files`.

    The JSON includes:
      - `sample_id`
      - `speaker_a`, `speaker_b`
      - every `session_<i>` and `session_<i>_date_time` key, in original order
    """
    payload: dict[str, object] = {"sample_id": sample.sample_id}
    speaker_a = sample.conversation.get("speaker_a")
    speaker_b = sample.conversation.get("speaker_b")
    if speaker_a is not None:
        payload["speaker_a"] = speaker_a
    if speaker_b is not None:
        payload["speaker_b"] = speaker_b
    for key, value in sample.conversation.items():
        if key in ("speaker_a", "speaker_b"):
            continue
        if key.startswith("session_"):
            payload[key] = value

    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    filename = f"{sample.sample_id}_conversation.json"
    return [(filename, body)]
