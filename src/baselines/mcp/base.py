"""MCP-memory-on-harness baseline.

Composes a `Harness` (e.g. Claude Code) with an `McpMemoryBackend` (e.g.
`memory_md_mcp`) and exposes them through the existing `Baseline` lifecycle, so
`run_sample`, aggregation, Mongo, and reporting work unchanged. The lifecycle
deliberately mirrors `PamBaseline`: build memory per sample, then answer
batched questions with retries, inter-batch spacing, structured logging, and the
same numbered Q/A protocol.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from baselines.base import BaselineBase, BaselineResponse, TokenUsage, split_input_tokens
from batch_protocol import count_tokens, distribute, parse_batch_response, render_batch_prompt
from datasets.locomo.schemas import LoCoMoSample
from harnesses.base import Harness, HarnessResult

from .serialize import conversation_to_transcript

logger = logging.getLogger(__name__)


@runtime_checkable
class McpMemoryBackend(Protocol):
    """How an agent stores/recalls memory — independent of which harness runs it."""

    name: str

    async def setup(self) -> None: ...
    def mcp_servers(self, memory_dir: Path) -> dict | None: ...
    def allowed_tools(self, phase: str) -> list[str]: ...  # phase: "ingest" | "answer"
    def ingest_prompt(self, conversation_text: str) -> str: ...
    def answer_prompt(self, batch_prompt: str) -> str: ...
    async def reset(self, memory_dir: Path) -> None: ...
    def memory_exists(self, memory_dir: Path) -> bool: ...


class McpHarnessBaseline(BaselineBase):
    """A memory MCP baseline running on top of an agentic harness."""

    track = "agentic_memory"
    external_memory = True

    # Same tunables as PamBaseline (tests override to 0).
    INTER_BATCH_SLEEP_SEC: float = 5.0
    MAX_BATCH_RETRIES: int = 2
    BATCH_RETRY_BASE_SLEEP_SEC: float = 5.0

    def __init__(
        self,
        *,
        harness: Harness,
        backend: McpMemoryBackend,
        output_root: Path,
        batch_size: int = 10,
        harness_model: str | None = None,
        keep_memory: bool = False,
        max_turns: int | None = None,
        **_ignored: Any,
    ) -> None:
        self.harness = harness
        self.backend = backend
        self.name = backend.name
        self._output_root = Path(output_root)
        self.batch_size = max(1, int(batch_size or 1))
        self._harness_model = harness_model or getattr(harness, "model", None)
        self._keep_memory = bool(keep_memory)
        self._max_turns = max_turns

        self._memory_dir: Path | None = None
        self._memory_creation_sec: float = 0.0
        self._current_sample_id: str | None = None
        self._build_usage: dict[str, Any] = {}
        self._session_ids: list[str] = []
        # Batch progress within the current sample.
        self._batch_index: int = 0
        self._total_batches: int = 0

    # ----- lifecycle ------------------------------------------------------

    async def setup(self, *, seed: int) -> None:
        logger.info(
            "Initializing harness=%s backend=%s (model=%s)...",
            self.harness.name,
            self.backend.name,
            self._harness_model,
        )
        await self.harness.setup()
        await self.backend.setup()
        logger.info("Harness ready (auth resolved).")

    async def prepare_for_sample(self, sample: LoCoMoSample) -> None:
        self._current_sample_id = sample.sample_id
        self._memory_creation_sec = 0.0
        self._build_usage = {}
        self._session_ids = []
        self._batch_index = 0
        self._total_batches = (len(sample.qa) + self.batch_size - 1) // self.batch_size

        memory_dir = self._output_root / sample.sample_id / "memory"
        self._memory_dir = memory_dir

        # Debug reuse: if memory is already built (kept from a prior run), skip
        # the build and answer against it directly.
        if self._keep_memory and self.backend.memory_exists(memory_dir):
            logger.info(
                "MCP debug: reusing existing memory for sample=%s at %s",
                sample.sample_id,
                memory_dir,
            )
            return

        await self.backend.reset(memory_dir)
        transcript = conversation_to_transcript(sample)

        logger.info(
            "Claude Code: building memory for sample=%s "
            "(model=%s, %d questions / %d batches, transcript=%d chars) — this can take a "
            "few minutes...",
            sample.sample_id,
            self._harness_model,
            len(sample.qa),
            self._total_batches,
            len(transcript),
        )
        loop = asyncio.get_running_loop()
        t0 = loop.time()
        result = await self.harness.run(
            prompt=self.backend.ingest_prompt(transcript),
            working_dir=memory_dir,
            allowed_tools=self.backend.allowed_tools("ingest"),
            mcp_servers=self.backend.mcp_servers(memory_dir),
            max_turns=self._max_turns,
        )
        self._memory_creation_sec = round(loop.time() - t0, 2)
        self._record_session(result)
        self._build_usage = {
            "memory_build_input_tokens": result.input_tokens,
            "memory_build_output_tokens": result.output_tokens,
            "memory_build_cache_read_tokens": result.cache_read_tokens,
            "memory_build_cache_write_tokens": result.cache_write_tokens,
            "memory_build_cost_usd": round(result.cost_usd, 6),
        }
        note_count = self._count_notes(memory_dir)
        logger.info(
            "Claude Code built memory for sample=%s in %.2fs (notes=%d, model=%s, cost=$%.4f)",
            sample.sample_id,
            self._memory_creation_sec,
            note_count,
            self._harness_model,
            result.cost_usd,
        )

    async def answer(self, prompt: str, *, max_tokens: int | None = None) -> BaselineResponse:
        responses = await self.answer_batch([prompt])
        return responses[0]

    async def answer_batch(self, prompts: list[str]) -> list[BaselineResponse]:
        if not prompts:
            return []
        assert self._memory_dir is not None

        rendered = render_batch_prompt(prompts)
        n = len(prompts)
        self._batch_index += 1
        batch_no = self._batch_index
        total_batches = self._total_batches or batch_no

        if batch_no > 1 and self.INTER_BATCH_SLEEP_SEC > 0:
            await asyncio.sleep(self.INTER_BATCH_SLEEP_SEC)

        # prompt_tokens = tokens of the prompt we send (counted with the harness
        # model's tokenizer), split evenly across the batch's questions.
        prompt_share = distribute(count_tokens(self._harness_model, rendered), n)

        logger.info(
            "Claude Code: asking batch %d/%d (%d questions) for sample=%s — waiting for answer...",
            batch_no,
            total_batches,
            n,
            self._current_sample_id,
        )

        # Run the harness; retry on a fully-empty (0/N) reply with exp. backoff.
        result: HarnessResult | None = None
        parsed: list[str] = [""] * n
        answered = 0
        last_exc: Exception | None = None
        attempts_total = self.MAX_BATCH_RETRIES + 1
        for attempt in range(attempts_total):
            if attempt > 0:
                delay = self.BATCH_RETRY_BASE_SLEEP_SEC * (2 ** (attempt - 1))
                logger.warning(
                    "Claude Code batch %d/%d got 0/%d answers; retry %d/%d after %.0fs",
                    batch_no,
                    total_batches,
                    n,
                    attempt,
                    self.MAX_BATCH_RETRIES,
                    delay,
                )
                if delay > 0:
                    await asyncio.sleep(delay)
            try:
                result = await self.harness.run(
                    prompt=self.backend.answer_prompt(rendered),
                    working_dir=self._memory_dir,
                    allowed_tools=self.backend.allowed_tools("answer"),
                    mcp_servers=self.backend.mcp_servers(self._memory_dir),
                    max_turns=self._max_turns,
                )
                parsed = parse_batch_response(result.text, n)
                last_exc = None
            except Exception as e:
                last_exc = e
                result = None
                parsed = [""] * n
                logger.warning(
                    "Claude Code run failed for batch %d/%d (%d questions), attempt %d/%d: %r",
                    batch_no,
                    total_batches,
                    n,
                    attempt + 1,
                    attempts_total,
                    e,
                )
            answered = sum(1 for a in parsed if a)
            if answered > 0:
                break

        if result is None and last_exc is not None:
            return [self._empty_response(0.0, prompt_tokens=prompt_share[i]) for i in range(n)]

        assert result is not None
        self._record_session(result)
        logger.info(
            "Claude Code answered %d/%d questions in batch %d/%d for sample=%s (%.0f ms, cost=$%.4f)",
            answered,
            n,
            batch_no,
            total_batches,
            self._current_sample_id,
            result.duration_ms,
            result.cost_usd,
        )
        if answered < n:
            missing = [i + 1 for i, a in enumerate(parsed) if not a]
            logger.warning(
                "Claude Code batch %d/%d reply missing answers for slots %s (batch size=%d)",
                batch_no,
                total_batches,
                missing,
                n,
            )

        # Distribute the single batch run's usage across the questions.
        # `input_tokens` = the TOTAL input the model processed = fresh +
        # cache-read + cache-write. Claude Code reports `input_tokens` as the
        # non-cached delta only; with prompt caching the bulk of the batch prompt
        # and the memory files re-read across agentic turns land in cache-read,
        # so non-cached alone would be tiny and misleading. The non-cached part
        # is still kept as `agent_input_tokens` (so agent_input + cache_read +
        # cache_write == input_tokens).
        total_input = result.input_tokens + result.cache_read_tokens + result.cache_write_tokens
        in_share = distribute(total_input, n)
        agent_in_share = distribute(result.input_tokens, n)
        out_share = distribute(result.output_tokens, n)
        cr_share = distribute(result.cache_read_tokens, n)
        cw_share = distribute(result.cache_write_tokens, n)
        per_q_latency = result.duration_ms / n
        per_q_cost = result.cost_usd / n

        out: list[BaselineResponse] = []
        for i, answer in enumerate(parsed):
            prompt_tok, context_tok = split_input_tokens(in_share[i], prompt_share[i])
            out.append(
                BaselineResponse(
                    text=answer,
                    usage=TokenUsage(
                        input_tokens=in_share[i],
                        output_tokens=out_share[i],
                        prompt_tokens=prompt_tok,
                        context_tokens=context_tok,
                        est_cost_usd=per_q_cost,
                        # injected/enriched are Pam-only concepts.
                        injected_tokens=None,
                        enriched_user_prompt_tokens=None,
                        agent_input_tokens=agent_in_share[i],
                        agent_output_tokens=out_share[i],
                        agent_cache_read_tokens=cr_share[i],
                        agent_cache_write_tokens=cw_share[i],
                    ),
                    latency_ms=per_q_latency,
                    raw={"raw_prompt": rendered, "raw_response": result.text},
                )
            )
        return out

    async def cleanup_sample(self) -> None:
        # Keep the per-sample memory only in debug mode; otherwise wipe it.
        if self._keep_memory or self._memory_dir is None:
            return
        sample_dir = self._memory_dir.parent
        await asyncio.to_thread(shutil.rmtree, sample_dir, True)

    async def teardown(self) -> None:
        await self.harness.teardown()

    def extras(self) -> dict[str, Any]:
        return {
            "memory_creation_duration_sec": self._memory_creation_sec,
            "harness": self.harness.name,
            "harness_model": self._harness_model,
            "batch_size": self.batch_size,
            "memory_dir": str(self._memory_dir) if self._memory_dir else None,
            "harness_session_ids": list(self._session_ids),
            **self._build_usage,
        }

    def baseline_kwargs_extra(self) -> dict[str, Any]:
        # `memory_backend` is omitted — it equals `baseline` for MCP baselines.
        return {
            "harness": self.harness.name,
            "harness_model": self._harness_model,
        }

    # ----- helpers --------------------------------------------------------

    def _record_session(self, result: HarnessResult) -> None:
        if result.session_id:
            self._session_ids.append(result.session_id)

    @staticmethod
    def _count_notes(memory_dir: Path) -> int:
        notes = memory_dir / "notes"
        return len(list(notes.glob("*.md"))) if notes.exists() else 0

    def _empty_response(self, latency_ms: float, prompt_tokens: int = 0) -> BaselineResponse:
        return BaselineResponse(
            text="",
            usage=TokenUsage(
                input_tokens=0,
                output_tokens=0,
                prompt_tokens=prompt_tokens,
                context_tokens=0,
                est_cost_usd=0.0,
                injected_tokens=None,
                enriched_user_prompt_tokens=None,
            ),
            latency_ms=latency_ms,
            raw={"raw_response": "<harness run failed>"},
        )
