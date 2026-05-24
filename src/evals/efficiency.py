"""Token efficiency helpers (counts already come from the baseline response).

This module currently exists for symmetry with the plan; baselines already
record `input_tokens`/`output_tokens` via the provider's usage record. Use
the helpers below when a prompt's token count is needed *before* an API call
(e.g. budget arithmetic in prompt building) or when a baseline doesn't
return usage and we need to fall back to a tokenizer estimate.
"""

from __future__ import annotations

import tiktoken


def count_tokens(text: str, *, model: str = "gpt-4o") -> int:
    try:
        enc = tiktoken.encoding_for_model(model)
    except (KeyError, ValueError):
        enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))
