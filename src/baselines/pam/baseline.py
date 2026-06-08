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
import os
import re
import time
import uuid
from typing import Any

import litellm

from baselines.base import BaselineBase, BaselineResponse, TokenUsage
from baselines.pam.client import PamClient
from baselines.pam.metrics_db import AgentMetrics, PamMetricsReader
from baselines.pam.serialize import serialize_sample
from datasets.locomo.schemas import LoCoMoSample
from env import require

logger = logging.getLogger(__name__)

# Output-token estimate via a fixed counter so the report shows a comparable
# value alongside other baselines. Pam does not expose the underlying LLM's
# token usage directly. The counter's model id is a secret — supplied via this
# env var (set it in secrets.env / Secret Manager), never hardcoded.
_OUTPUT_TOKEN_MODEL_ENV = "PAM_OUTPUT_TOKEN_MODEL"


def _count_tokens(model: str | None, text: str) -> int:
    """Token count of `text` per the configured model's tokenizer (0 if no model
    is set or counting fails). Used for both the prompt and the answer."""
    if not text or not model:
        return 0
    try:
        return int(litellm.token_counter(model=model, text=text))
    except Exception:
        return 0


def _distribute(total: int, n: int) -> list[int]:
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
# <final>...</final> block. The SSE stream can even begin mid-thought (the
# opening <think> already gone), so the reasoning text gets glued onto the same
# line as the first answer, e.g.
#   ...output it exactly as requested.</think><final>A1: Progressive/liberal
# which leaves `A1:` off the line start and drops slot 1. Cutting everything up
# to the last such boundary tag restores a clean `A1:`-first answer block.
_SCAFFOLD_BOUNDARIES = ("</think>", "<final>")


def _strip_reasoning_scaffold(text: str) -> str:
    cut = 0
    for marker in _SCAFFOLD_BOUNDARIES:
        idx = text.rfind(marker)
        if idx != -1:
            cut = max(cut, idx + len(marker))
    if cut:
        text = text[cut:]
    return text.replace("</final>", "").strip()


def _render_batch_prompt(prompts: list[str]) -> str:
    """Render a numbered Q1..QN prompt asking for A1..AN-formatted answers.

    The format rules are deliberately strict: Pam sits behind a tool-using agent
    that sometimes streams status narration ("I'm searching your memory...") or
    wraps its reply in reasoning tags, and occasionally drops the "A" prefix on a
    line. The instructions below push it toward a clean, complete answer block so
    every slot parses; the parser is tolerant of the rest.
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
    """Extract `n_expected` answers from a numbered-reply Pam response.

    Lines that start with `A<i>:` (or `A<i>.` / `A<i>)`) are captured and
    associated with question `i`. Continuation lines (no `Ai:` prefix) are
    appended to the most recently captured answer. Missing slots get empty
    strings — the caller logs a warning so the F1/judge pipeline still sees
    something for each question.

    A leading <think>/<final> reasoning scaffold (which can land glued onto the
    first answer line) is stripped first — see `_strip_reasoning_scaffold`. A
    line that drops the "A" prefix ("9:" instead of "A9:") is recovered when its
    number is the next expected slot.
    """
    text = _strip_reasoning_scaffold(text)
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
        backup_memory: bool = False,
        api_key: str | None = None,
        **_ignored: Any,
    ) -> None:
        # PAM_API_KEY is optional: only debug mode (`--pam-debug-user-id`) needs
        # it, to mint a per-user token for the reused account. A normal run
        # never touches it, so don't `require` it here.
        self._api_key = api_key or os.environ.get("PAM_API_KEY")
        self.client = PamClient(host or require("PAM_API_HOST"), api_key=self._api_key)
        self._admin_email = admin_email or require("PAM_API_USER")
        self._admin_password = admin_password or require("PAM_API_PASSWORD")
        self.batch_size = max(1, int(batch_size or 1))
        self._debug_user_id = debug_user_id
        # When True, the account is preserved entirely (not deleted) so it can
        # be reused later via --pam-debug-user-id. See `cleanup_sample`.
        self._backup_memory = bool(backup_memory)

        # Model id whose tokenizer counts Pam's output tokens — supplied via env
        # (secret), never hardcoded. Missing => output_tokens fall back to 0.
        self._output_token_model = os.environ.get(_OUTPUT_TOKEN_MODEL_ENV)
        if not self._output_token_model:
            logger.warning(
                "%s not set; Pam output_tokens will be reported as 0",
                _OUTPUT_TOKEN_MODEL_ENV,
            )

        # Reads agent-side token usage from Pam's `message_metrics` table after
        # each answer. `_last_metrics_id` is the newest row seen so far for the
        # current user — used to wait out write-lag so we read THIS turn's row,
        # not a stale one. `_agent_model_used` is surfaced into baseline_kwargs.
        self._metrics_reader = PamMetricsReader()
        self._last_metrics_id: Any = None
        self._agent_model_used: str | None = None

        self._memory_creation_sec: float = 0.0
        self._pam_user_id: int | None = None
        self._current_sample_id: str | None = None
        self._last_memory_run_ids: list[str] = []

    # ----- lifecycle ------------------------------------------------------

    async def setup(self, *, seed: int) -> None:
        await asyncio.to_thread(self.client.login, self._admin_email, self._admin_password)

    async def prepare_for_sample(self, sample: LoCoMoSample) -> None:
        self._current_sample_id = sample.sample_id
        self._memory_creation_sec = 0.0

        if self._debug_user_id is not None:
            # Reuse an existing Pam user (e.g. one kept alive by a prior
            # --backup-memory run) — skip create / upload / memory build and go
            # straight to asking questions against its existing memory.
            #
            # `messages/stream` answers from whichever user the bearer token
            # belongs to, so we must run as the reused user, NOT as admin. Mint
            # a per-user access token for `debug_user_id` via the api-key admin
            # endpoint and use it for the SSE chat calls.
            await asyncio.to_thread(self.client.issue_user_tokens, self._debug_user_id)
            self._pam_user_id = self._debug_user_id
            logger.info(
                "Pam debug mode: reusing user_id=%s (minted per-user token) for sample=%s",
                self._debug_user_id,
                sample.sample_id,
            )
            await self._capture_metrics_baseline()
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

        # 2. Process generic files: uploads the conversation JSON AND kicks
        # off the memory pipeline in one call per batch (max 5 files per call).
        # Returns the run_id(s) we then poll for completion.
        files = serialize_sample(sample)
        mem_start = time.time()
        run_ids = await asyncio.to_thread(self.client.process_generic_files, files)
        self._last_memory_run_ids = list(run_ids)
        logger.info(
            "Pam process_generic_files for sample=%s (user_id=%s) -> run_ids=%s",
            sample.sample_id,
            self._pam_user_id,
            run_ids,
        )

        # 3. Poll each memory pipeline run until terminal status. Raises
        # RuntimeError on `failed`; returns once all runs are `completed`.
        await asyncio.to_thread(self.client.wait_for_memory, run_ids)
        self._memory_creation_sec = round(time.time() - mem_start, 2)
        logger.info(
            "Pam memory built for sample=%s in %.2fs (run_ids=%s)",
            sample.sample_id,
            self._memory_creation_sec,
            run_ids,
        )
        await self._capture_metrics_baseline()

    async def _capture_metrics_baseline(self) -> None:
        """Record the newest existing `message_metrics` id for the current user
        so the next answer can tell its own fresh row from pre-existing ones."""
        m = await self._metrics_reader.latest_for_user(self._pam_user_id)
        self._last_metrics_id = m.metrics_id if m else None

    async def _read_agent_metrics(self) -> AgentMetrics | None:
        """Fetch the metrics row written for the prompt we just sent.

        Filters by user_id, orders by created_at desc, takes the first row. The
        agent writes the row while streaming, so it normally exists already; if
        write-lag means the newest row is still the previous turn's, retry a few
        times before giving up."""
        uid = self._pam_user_id
        m = await self._metrics_reader.latest_for_user(uid)
        attempts = 0
        while m is not None and m.metrics_id == self._last_metrics_id and attempts < 5:
            await asyncio.sleep(0.4)
            m = await self._metrics_reader.latest_for_user(uid)
            attempts += 1
        if m is not None:
            self._last_metrics_id = m.metrics_id
            if m.agent_model_used:
                self._agent_model_used = m.agent_model_used
        return m

    async def answer(self, prompt: str, *, max_tokens: int | None = None) -> BaselineResponse:
        responses = await self.answer_batch([prompt])
        return responses[0]

    async def answer_batch(self, prompts: list[str]) -> list[BaselineResponse]:
        if not prompts:
            return []

        rendered = _render_batch_prompt(prompts)
        n = len(prompts)

        # prompt_tokens = tokens of the prompt WE send to Pam (the rendered
        # Q1..QN batch). It's always measurable and independent of whether Pam
        # exposes its input usage, so it stays > 0 even though input/context are
        # 0. The batch shares one prompt, so split it evenly across its questions.
        prompt_share = _distribute(_count_tokens(self._output_token_model, rendered), n)

        t0 = time.perf_counter()
        try:
            answer_text, injected_total = await asyncio.to_thread(
                self.client.send_message, rendered
            )
        except Exception as e:
            logger.warning("Pam send_message failed for batch of %d: %r", n, e)
            # Surface as empty answers so downstream scorers still get rows.
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            raw = {"raw_prompt": rendered, "raw_response": f"<send_message failed: {e!r}>"}
            return [
                self._empty_response(elapsed_ms / n, raw=raw, prompt_tokens=prompt_share[i])
                for i in range(n)
            ]

        total_latency_ms = (time.perf_counter() - t0) * 1000.0

        # One Pam agent call answered the whole batch → one message_metrics row.
        # Read it and distribute its per-batch token totals across the batch's
        # questions (same even-split treatment as injected_tokens).
        metrics = await self._read_agent_metrics()

        parsed = parse_batch_response(answer_text, n)
        if any(not a for a in parsed):
            missing = [i + 1 for i, a in enumerate(parsed) if not a]
            logger.warning(
                "Pam batch reply missing answers for slots %s (batch size=%d)",
                missing,
                n,
            )

        per_question_latency = total_latency_ms / n
        per_question_injected = injected_total // n if injected_total else 0
        agent_in = _distribute(metrics.agent_input_tokens if metrics else 0, n)
        agent_out = _distribute(metrics.agent_output_tokens if metrics else 0, n)
        agent_cr = _distribute(metrics.agent_cache_read_tokens if metrics else 0, n)
        agent_cw = _distribute(metrics.agent_cache_write_tokens if metrics else 0, n)
        enriched = _distribute(metrics.enriched_user_prompt_tokens if metrics else 0, n)

        out: list[BaselineResponse] = []
        for i, answer in enumerate(parsed):
            out.append(
                BaselineResponse(
                    text=answer,
                    usage=TokenUsage(
                        # Pam does not expose the underlying model's input usage,
                        # so input/context tokens stay 0. prompt_tokens is the
                        # count of the prompt we sent (see prompt_share above).
                        input_tokens=0,
                        output_tokens=_count_tokens(self._output_token_model, answer),
                        prompt_tokens=prompt_share[i],
                        context_tokens=0,
                        est_cost_usd=0.0,
                        injected_tokens=per_question_injected,
                        # Agent-side usage from the message_metrics row.
                        agent_input_tokens=agent_in[i],
                        agent_output_tokens=agent_out[i],
                        agent_cache_read_tokens=agent_cr[i],
                        agent_cache_write_tokens=agent_cw[i],
                        enriched_user_prompt_tokens=enriched[i],
                    ),
                    latency_ms=per_question_latency,
                    # The whole batch shares one Pam exchange: the rendered Q1..QN
                    # prompt and the full A1..AN reply (before per-question split).
                    # Surfaced for the --save-responses debug log.
                    raw={"raw_prompt": rendered, "raw_response": answer_text},
                )
            )
        return out

    async def cleanup_sample(self) -> None:
        # Delete the account for the just-finished conversation. Doing this
        # per-sample (instead of deferring to teardown) avoids leaving stale
        # users around and prevents memory versions from accumulating server-side.
        # `_pam_user_id` / `_current_sample_id` are intentionally NOT cleared
        # here so the runner can still read them via `extras()` for the Mongo
        # doc; the next `prepare_for_sample` overwrites them.
        if self._debug_user_id is not None:
            logger.info("Pam debug mode: skipping delete_account")
            return
        if self._backup_memory:
            # `--backup-memory`: keep the whole account (and its built memory)
            # so it can be reused later via `--pam-debug-user-id`. Nothing is
            # deleted — no records, no memory.
            logger.info(
                "Pam backup mode: preserving user_id=%s (account NOT deleted)",
                self._pam_user_id,
            )
            return
        uid = self._pam_user_id
        if uid is None:
            return
        try:
            await asyncio.to_thread(self.client.delete_account, user_id=uid)
            logger.info("Pam deleted user_id=%s", uid)
        except Exception as e:
            logger.warning("Pam delete_account failed for user_id=%s: %r", uid, e)

    async def teardown(self) -> None:
        await self._metrics_reader.close()

    def extras(self) -> dict[str, Any]:
        return {
            "memory_creation_duration_sec": self._memory_creation_sec,
            "pam_user_id": self._pam_user_id,
            "pam_batch_size": self.batch_size,
            "pam_memory_run_ids": list(self._last_memory_run_ids),
        }

    def baseline_kwargs_extra(self) -> dict[str, Any]:
        """Extra entries merged into the Mongo doc's `baseline_kwargs`. Carries
        the agent model id read from `message_metrics` (string, not a token
        count, so it rides here rather than through the token aggregation)."""
        if self._agent_model_used:
            return {"agent_model_used": self._agent_model_used}
        return {}

    def _empty_response(
        self, latency_ms: float, raw: dict[str, Any] | None = None, prompt_tokens: int = 0
    ) -> BaselineResponse:
        return BaselineResponse(
            text="",
            usage=TokenUsage(
                input_tokens=0,
                output_tokens=0,
                prompt_tokens=prompt_tokens,
                context_tokens=0,
                est_cost_usd=0.0,
                injected_tokens=0,
            ),
            latency_ms=latency_ms,
            raw=raw or {},
        )
