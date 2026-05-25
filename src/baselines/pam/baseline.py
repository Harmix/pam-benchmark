"""Pam baseline — drives Harmix's Pam memory layer through the harness.

Lifecycle (per LoCoMo sample):
  1. `setup`             — admin login.
  2. `prepare_for_sample` — create user (or reuse `--pam-debug-user-id`),
                            upload the sample's `*_conversation.json`,
                            trigger and poll the memory pipeline.
  3. `answer_batch`       — one SSE chat call per chunk of questions; numbered
                            Qi/Ai protocol so multiple questions share one
                            memory retrieval.
  4. `cleanup_sample`     — delete the user account (skipped in debug mode).
  5. `teardown`           — no-op.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from typing import Any

import tiktoken

from baselines.base import BaselineBase, BaselineResponse, TokenUsage
from baselines.pam.client import PamClient
from baselines.pam.serialize import serialize_sample
from datasets.locomo.schemas import LoCoMoSample
from env import require

logger = logging.getLogger(__name__)

# Output-token estimate via a fixed encoder so the report shows a comparable
# value alongside other baselines. Pam does not expose the underlying LLM's
# token usage directly.
_OUTPUT_TOKEN_ENCODER_NAME = "cl100k_base"


_ANSWER_LINE_RE = re.compile(r"^\s*A(\d+)\s*[:\.\)]\s*(.*)$", re.IGNORECASE)


def _render_batch_prompt(prompts: list[str]) -> str:
    """Render a numbered Q1..QN prompt asking for A1..AN-formatted answers."""
    questions_block = "\n".join(f"Q{i}: {p}" for i, p in enumerate(prompts, start=1))
    template_block = "\n".join(f"A{i}: <short answer>" for i in range(1, len(prompts) + 1))
    return (
        "Answer each of the following questions about the conversation in memory.\n"
        "Reply in the EXACT format below, one answer per line, with the number "
        "matching the question. Keep each answer concise.\n\n"
        f"{template_block}\n\n"
        f"{questions_block}"
    )


def parse_batch_response(text: str, n_expected: int) -> list[str]:
    """Extract `n_expected` answers from a numbered-reply Pam response.

    Lines that start with `A<i>:` (or `A<i>.` / `A<i>)`) are captured and
    associated with question `i`. Continuation lines (no `Ai:` prefix) are
    appended to the most recently captured answer. Missing slots get empty
    strings — the caller logs a warning so the F1/judge pipeline still sees
    something for each question.
    """
    answers: dict[int, list[str]] = {}
    current_idx: int | None = None

    for raw_line in text.splitlines():
        m = _ANSWER_LINE_RE.match(raw_line)
        if m:
            current_idx = int(m.group(1))
            answers.setdefault(current_idx, []).append(m.group(2).strip())
        elif current_idx is not None and raw_line.strip():
            answers[current_idx].append(raw_line.strip())

    out: list[str] = []
    for i in range(1, n_expected + 1):
        parts = answers.get(i, [])
        joined = " ".join(p for p in parts if p).strip()
        out.append(joined)
    return out


class PamBaseline(BaselineBase):
    """Pam memory baseline."""

    name = "pam"
    track = "memory_product"
    external_memory = True

    def __init__(
        self,
        host: str | None = None,
        admin_email: str | None = None,
        admin_password: str | None = None,
        *,
        batch_size: int = 10,
        debug_user_id: int | None = None,
        **_ignored: Any,
    ) -> None:
        self.client = PamClient(host or require("PAM_API_HOST"))
        self._admin_email = admin_email or require("PAM_API_USER")
        self._admin_password = admin_password or require("PAM_API_PASSWORD")
        self.batch_size = max(1, int(batch_size or 1))
        self._debug_user_id = debug_user_id

        self._encoder = tiktoken.get_encoding(_OUTPUT_TOKEN_ENCODER_NAME)
        self._memory_creation_sec: float = 0.0
        self._pam_user_id: int | None = None
        self._current_sample_id: str | None = None

    # ----- lifecycle ------------------------------------------------------

    async def setup(self, *, seed: int) -> None:
        await asyncio.to_thread(self.client.login, self._admin_email, self._admin_password)

    async def prepare_for_sample(self, sample: LoCoMoSample) -> None:
        self._current_sample_id = sample.sample_id
        self._memory_creation_sec = 0.0

        if self._debug_user_id is not None:
            # Reuse an existing Pam user — skip create / upload / memory build.
            self.client.user_id = self._debug_user_id
            # Use the admin token; in debug mode there's no per-user login.
            self.client.access_token = self.client.admin_token
            self._pam_user_id = self._debug_user_id
            logger.info(
                "Pam debug mode: reusing user_id=%s for sample=%s",
                self._debug_user_id,
                sample.sample_id,
            )
            return

        # 1. Create per-sample user (unique email keeps Pam state isolated).
        suffix = uuid.uuid4().hex[:8]
        email = f"locomo-{sample.sample_id}-{int(time.time())}-{suffix}@benchmark.local"
        await asyncio.to_thread(
            self.client.create_account,
            email=email,
            password="benchmark-run",
            name=f"LoCoMo {sample.sample_id}",
        )
        self._pam_user_id = self.client.user_id
        logger.info("Pam created user_id=%s for sample=%s", self._pam_user_id, sample.sample_id)

        # 2. Upload the single conversation JSON.
        files = serialize_sample(sample)
        await asyncio.to_thread(self.client.upload_generic_files, files)
        logger.info(
            "Pam uploaded %d file(s) for sample=%s (user_id=%s)",
            len(files),
            sample.sample_id,
            self._pam_user_id,
        )

        # 3. Build memory (long-poll on the Pam side; tolerate transient errors).
        mem_start = time.time()
        await asyncio.to_thread(self.client.create_memory)
        self._memory_creation_sec = round(time.time() - mem_start, 2)
        logger.info(
            "Pam memory built for sample=%s in %.2fs",
            sample.sample_id,
            self._memory_creation_sec,
        )

    async def answer(self, prompt: str, *, max_tokens: int | None = None) -> BaselineResponse:
        responses = await self.answer_batch([prompt])
        return responses[0]

    async def answer_batch(self, prompts: list[str]) -> list[BaselineResponse]:
        if not prompts:
            return []

        rendered = _render_batch_prompt(prompts)
        t0 = time.perf_counter()
        try:
            answer_text, injected_total = await asyncio.to_thread(
                self.client.send_message, rendered
            )
        except Exception as e:
            logger.warning("Pam send_message failed for batch of %d: %r", len(prompts), e)
            # Surface as empty answers so downstream scorers still get rows.
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return [self._empty_response(elapsed_ms / len(prompts)) for _ in prompts]

        total_latency_ms = (time.perf_counter() - t0) * 1000.0
        parsed = parse_batch_response(answer_text, len(prompts))
        if any(not a for a in parsed):
            missing = [i + 1 for i, a in enumerate(parsed) if not a]
            logger.warning(
                "Pam batch reply missing answers for slots %s (batch size=%d)",
                missing,
                len(prompts),
            )

        per_question_latency = total_latency_ms / len(prompts)
        per_question_injected = injected_total // len(prompts) if injected_total else 0

        out: list[BaselineResponse] = []
        for answer in parsed:
            out_tokens = len(self._encoder.encode(answer)) if answer else 0
            out.append(
                BaselineResponse(
                    text=answer,
                    usage=TokenUsage(
                        input_tokens=0,
                        output_tokens=out_tokens,
                        est_cost_usd=0.0,
                        injected_tokens=per_question_injected,
                    ),
                    latency_ms=per_question_latency,
                    raw={},
                )
            )
        return out

    async def cleanup_sample(self) -> None:
        if self._debug_user_id is not None:
            logger.info("Pam debug mode: skipping delete_account")
            return
        if self.client.user_id is None:
            return
        try:
            await asyncio.to_thread(self.client.delete_account)
            logger.info("Pam deleted user_id=%s", self._pam_user_id)
        except Exception as e:
            logger.warning("Pam delete_account failed for user_id=%s: %r", self._pam_user_id, e)

    async def teardown(self) -> None:
        return None

    def extras(self) -> dict[str, Any]:
        return {
            "memory_creation_duration_sec": self._memory_creation_sec,
            "pam_user_id": self._pam_user_id,
            "pam_batch_size": self.batch_size,
        }

    def _empty_response(self, latency_ms: float) -> BaselineResponse:
        return BaselineResponse(
            text="",
            usage=TokenUsage(input_tokens=0, output_tokens=0, est_cost_usd=0.0, injected_tokens=0),
            latency_ms=latency_ms,
            raw={},
        )
