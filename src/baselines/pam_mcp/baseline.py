"""`pam_mcp` baseline — Pam server-side memory, answered via a harness + MCP.

A hybrid of the two existing baselines:
  * Memory is built **server-side via the Pam API** (identical to `pam`):
    create a per-conversation account, upload the conversation, poll the memory
    pipeline.
  * Questions are answered by an **agentic harness (Claude Code) using the PAM
    Memory MCP tool** (`retrieve_memory`) instead of Pam's chat endpoint.

Lifecycle (per LoCoMo sample), mirroring `PamBaseline`:
  1. `setup`              — admin login + harness setup (Vertex auth).
  2. `prepare_for_sample` — create account on the MCP-only `dev` plan (which
                            grants MEMORY_MCP and skips agent-client provisioning),
                            or reuse `--pam-debug-user-id`; upload + build memory
                            (same polling as `pam`); then mint a Memory MCP key
                            via `/v1/dev/rotate-key`.
  3. `answer_batch`       — one Claude Code invocation per chunk of questions,
                            wired to the PAM Memory MCP server; numbered Qi/Ai
                            protocol with the same retry + inter-batch spacing.
  4. `cleanup_sample`     — delete the account (skipped in debug/backup mode).
  5. `teardown`           — harness teardown.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from baselines.base import BaselineBase, BaselineResponse, TokenUsage, split_input_tokens
from baselines.pam.client import PamClient
from baselines.pam.serialize import serialize_sample
from baselines.pam_mcp import prompts
from batch_protocol import (
    count_tokens,
    distribute,
    parse_batch_response,
    render_batch_prompt,
    strip_reasoning_scaffold,
)
from env import require
from harnesses.base import Harness, HarnessResult

logger = logging.getLogger(__name__)

# Credits plan the per-conversation account is created on. The MCP-only `dev`
# plan grants the MEMORY_MCP feature flag (needed to mint a Memory MCP key via
# the gated `/v1/dev/*` routes) and skips agent-client provisioning server-side.
_MCP_PLAN = "dev"

# Override the Memory MCP server URL; defaults to `<PAM_API_HOST>/v1/mcp/memory`.
_MCP_URL_ENV = "PAM_MCP_MEMORY_URL"


class PamMcpBaseline(BaselineBase):
    """Pam memory built server-side, answered through a harness + PAM Memory MCP."""

    name = "pam_mcp"
    track = "agentic_memory"
    external_memory = True

    # The MCP server name (as written into the harness `--mcp-config`) and the
    # resulting Claude Code tool id (`mcp__<server>__<tool>`).
    MCP_SERVER_NAME = "pam_memory"
    MCP_TOOL = "mcp__pam_memory__retrieve_memory"

    # Same tunables as PamBaseline / McpHarnessBaseline (tests override to 0).
    INTER_BATCH_SLEEP_SEC: float = 5.0
    MAX_BATCH_RETRIES: int = 2
    BATCH_RETRY_BASE_SLEEP_SEC: float = 5.0
    # Stagger between warming each avg@k pool session, so their MCP handshakes
    # don't cold-start all at once (which makes the tool fail to register).
    POOL_WARMUP_STAGGER_SEC: float = 3.0

    def __init__(
        self,
        *,
        harness: Harness,
        harness_model: str | None = None,
        output_root: Path,
        batch_size: int = 10,
        raw_prompt: bool = False,
        max_turns: int | None = None,
        max_batch_retries: int | None = None,
        samples_per_question: int = 1,
        debug_user_id: int | None = None,
        backup_memory: bool = False,
        mcp_url: str | None = None,
        host: str | None = None,
        admin_email: str | None = None,
        admin_password: str | None = None,
        api_key: str | None = None,
        save_responses: bool = False,
        **_ignored: Any,
    ) -> None:
        self.harness = harness
        self._harness_model = harness_model or getattr(harness, "model", None)
        self._output_root = Path(output_root)
        # Raw mode asks one question at a time with no answer-format scaffolding,
        # so batching is meaningless — pin batch size to 1.
        self._raw_prompt = bool(raw_prompt)
        self.batch_size = 1 if self._raw_prompt else max(1, int(batch_size or 1))
        self._max_turns = max_turns
        # Retries when a batch comes back empty (0/N) or answered without a
        # retrieval. Defaults to the class tunable; overridable per run so a
        # noisier environment can be given more headroom.
        self._max_batch_retries = (
            int(max_batch_retries) if max_batch_retries is not None else self.MAX_BATCH_RETRIES
        )
        # avg@k: K independent responses per question (raw mode only), generated in
        # parallel via a pool of K sessions and judged individually downstream. K=1
        # keeps a single session and the classic one-response-per-question path.
        self.samples_per_question = max(1, int(samples_per_question or 1))
        self._pool_size = self.samples_per_question if self._raw_prompt else 1
        # When set, the full harness transcript (thinking, tool calls, json
        # events) for every answer run is appended to harness.log in the output
        # dir, alongside responses.log.
        self._harness_log: Path | None = (
            self._output_root / "harness.log" if save_responses else None
        )

        # PAM_API_KEY is only needed for --pam-debug-user-id reuse (minting a
        # per-user token via the api-key-gated admin endpoint), exactly as for
        # the `pam` baseline. A normal run doesn't touch it.
        self._api_key = api_key or os.environ.get("PAM_API_KEY")
        self.client = PamClient(host or require("PAM_API_HOST"), api_key=self._api_key)
        self._admin_email = admin_email or require("PAM_API_USER")
        self._admin_password = admin_password or require("PAM_API_PASSWORD")
        self._debug_user_id = debug_user_id
        self._backup_memory = bool(backup_memory)

        host_clean = (host or require("PAM_API_HOST")).rstrip("/")
        self._mcp_url = mcp_url or os.environ.get(_MCP_URL_ENV) or f"{host_clean}/v1/mcp/memory"

        # Per-sample state.
        self._mcp_key: str | None = None
        self._mcp_key_prefix: str | None = None
        self._memory_creation_sec: float = 0.0
        self._pam_user_id: int | None = None
        self._current_sample_id: str | None = None
        self._last_memory_run_ids: list[str] = []
        self._scratch_dir: Path | None = None
        self._session_ids: list[str] = []
        self._batch_index: int = 0
        self._total_batches: int = 0
        # A pool of persistent Claude Code sessions per conversation (size
        # `_pool_size`: K for avg@k in raw mode, else 1). Each connects its MCP
        # server once (in prepare_for_sample), shares the one memory/MCP key, and
        # keeps its own conversation history — the K sessions give K parallel
        # trajectories for a question.
        self._sessions: list[Any] = []

    # ----- lifecycle ------------------------------------------------------

    async def setup(self, *, seed: int) -> None:
        await asyncio.to_thread(self.client.login, self._admin_email, self._admin_password)
        await self.harness.setup()
        if self._harness_log is not None:
            self._output_root.mkdir(parents=True, exist_ok=True)
            self._harness_log.unlink(missing_ok=True)  # fresh log per run
        logger.info("pam_mcp ready (admin login + harness auth resolved).")

    async def prepare_for_sample(self, sample: Any) -> None:
        self._current_sample_id = sample.sample_id
        self._memory_creation_sec = 0.0
        self._mcp_key = None
        self._mcp_key_prefix = None
        self._session_ids = []
        self._batch_index = 0
        self._total_batches = (len(sample.qa) + self.batch_size - 1) // self.batch_size

        self._scratch_dir = self._output_root / sample.sample_id / "scratch"
        self._scratch_dir.mkdir(parents=True, exist_ok=True)

        if self._debug_user_id is not None:
            # Reuse an existing Pam user (kept by a prior --backup-memory run):
            # skip create/upload/build, mint a per-user token, then a fresh MCP key.
            await asyncio.to_thread(self.client.issue_user_tokens, self._debug_user_id)
            self._pam_user_id = self._debug_user_id
            logger.info(
                "pam_mcp debug mode: reusing user_id=%s for sample=%s",
                self._debug_user_id,
                sample.sample_id,
            )
            await self._mint_mcp_key()
            return

        # 1. Create per-sample user on the MCP-only `dev` plan (unique email
        # keeps Pam state isolated). The plan grants MEMORY_MCP so the account
        # can mint a Memory MCP key below. One account per sample — for Harmix a
        # sample is one persona/environment, for LoCoMo one conversation.
        suffix = uuid.uuid4().hex[:8]
        email = f"bench-{sample.sample_id}-{int(time.time())}-{suffix}@benchmark.local"
        await asyncio.to_thread(
            self.client.create_account,
            email=email,
            password="benchmark-run",
            name=f"Bench {sample.sample_id}",
            plan=_MCP_PLAN,
        )
        self._pam_user_id = self.client.user_id
        logger.info("pam_mcp created user_id=%s for sample=%s", self._pam_user_id, sample.sample_id)

        # 2. Kick off the memory pipeline. Two paths:
        #   - snapshot datasets (Harmix): the memory is pre-staged in GCS, so
        #     the server copies the snapshot zip and runs extract for an
        #     explicit `--sources` list (skipping sources_download).
        #   - upload datasets (LoCoMo): serialize the conversation and upload it
        #     via process-generic-files (which zips it and runs extract_generic).
        mem_start = time.time()
        snapshot_uri = getattr(sample, "memory_snapshot", None)
        if snapshot_uri:
            sources = list(getattr(sample, "pipeline_sources", []) or [])
            run_id = await asyncio.to_thread(self.client.process_snapshot, snapshot_uri, sources)
            run_ids = [run_id]
            logger.info(
                "pam_mcp process_snapshot for sample=%s (user_id=%s) snapshot=%s "
                "sources=%s -> run_id=%s",
                sample.sample_id,
                self._pam_user_id,
                snapshot_uri,
                sources,
                run_id,
            )
        else:
            files = serialize_sample(sample)
            run_ids = await asyncio.to_thread(self.client.process_generic_files, files)
            logger.info(
                "pam_mcp process_generic_files for sample=%s (user_id=%s) -> run_ids=%s",
                sample.sample_id,
                self._pam_user_id,
                run_ids,
            )
        self._last_memory_run_ids = list(run_ids)

        # 3. Poll each memory pipeline run until terminal status (same polling).
        await asyncio.to_thread(self.client.wait_for_memory, run_ids)
        self._memory_creation_sec = round(time.time() - mem_start, 2)
        logger.info(
            "pam_mcp memory built for sample=%s in %.2fs (run_ids=%s)",
            sample.sample_id,
            self._memory_creation_sec,
            run_ids,
        )

        # 4. Mint a Memory MCP key (the `dev` plan already granted MEMORY_MCP).
        await self._mint_mcp_key()

    async def _mint_mcp_key(self) -> None:
        """Rotate a fresh Memory MCP key for the current user."""
        assert self._pam_user_id is not None
        key = await asyncio.to_thread(self.client.rotate_developer_key)
        self._mcp_key = key
        # Log only the non-secret prefix (`pam_mkey_<prefix>`), never the secret.
        self._mcp_key_prefix = key.split(".", 1)[0]
        logger.info(
            "pam_mcp minted Memory MCP key (prefix=%s) for user_id=%s",
            self._mcp_key_prefix,
            self._pam_user_id,
        )
        await self._open_sessions()

    async def _open_sessions(self) -> None:
        """Open the pool of `_pool_size` Claude Code sessions (each connects MCP once).

        Pool size is K for avg@k (raw mode), else 1. Each session gets its own
        working dir so their MCP configs don't collide, and shares the one MCP key.
        """
        await self._close_sessions()
        assert self._scratch_dir is not None
        for i in range(self._pool_size):
            work_dir = self._scratch_dir if self._pool_size == 1 else self._scratch_dir / f"pool{i}"
            self._sessions.append(
                self.harness.open_session(
                    working_dir=work_dir,
                    allowed_tools=[self.MCP_TOOL],
                    mcp_servers=self._mcp_servers(),
                    system=prompts.SYSTEM_PROMPT,
                    max_turns=self._max_turns,
                    log_path=self._harness_log,
                )
            )
        # Warm the pool ONE AT A TIME so the K MCP handshakes don't stampede on
        # the first question (concurrent cold-starts make the tool fail to
        # register). A single session cold-starts lazily as before.
        if self._pool_size > 1:
            for idx, session in enumerate(self._sessions):
                warmup = getattr(session, "warmup", None)
                if warmup is not None:
                    await warmup()
                    logger.info(
                        "pam_mcp warmed pool session %d/%d for sample=%s",
                        idx + 1,
                        self._pool_size,
                        self._current_sample_id,
                    )
                if idx < len(self._sessions) - 1 and self.POOL_WARMUP_STAGGER_SEC > 0:
                    await asyncio.sleep(self.POOL_WARMUP_STAGGER_SEC)

    async def _close_sessions(self) -> None:
        sessions, self._sessions = self._sessions, []
        for session in sessions:
            with contextlib.suppress(Exception):
                await session.aclose()

    def _mcp_servers(self) -> dict[str, Any]:
        return {
            self.MCP_SERVER_NAME: {
                "type": "http",
                "url": self._mcp_url,
                "headers": {"Authorization": self._mcp_key or ""},
            }
        }

    async def answer(self, prompt: str, *, max_tokens: int | None = None) -> BaselineResponse:
        responses = await self.answer_batch([prompt])
        return responses[0]

    async def _run_attempts(
        self,
        session: Any,
        base_prompt: str,
        *,
        batch_no: int,
        total_batches: int,
        n: int,
    ) -> tuple[HarnessResult | None, list[str], int, Exception | None]:
        """Send `base_prompt` on one session with the empty/no-retrieval retry loop.

        Returns `(result, parsed, answered, last_exc)`. First attempt sends the
        base prompt; retries prepend a firmer "you did NOT retrieve — call the tool
        now" preamble so the re-send forces the tool call instead of re-rolling.
        """
        result: HarnessResult | None = None
        parsed: list[str] = [""] * n
        answered = 0
        last_exc: Exception | None = None
        attempts_total = self._max_batch_retries + 1
        sent_prompt = base_prompt
        for attempt in range(attempts_total):
            if attempt > 0:
                delay = self.BATCH_RETRY_BASE_SLEEP_SEC * (2 ** (attempt - 1))
                logger.warning(
                    "pam_mcp batch %d/%d retry %d/%d after %.0fs "
                    "(previous attempt: empty or no retrieval)",
                    batch_no,
                    total_batches,
                    attempt,
                    self._max_batch_retries,
                    delay,
                )
                sent_prompt = prompts.retrieval_retry_prefix(self.MCP_TOOL) + base_prompt
                if delay > 0:
                    await asyncio.sleep(delay)
            try:
                # One turn on a per-conversation session — MCP is already connected
                # (from prepare_for_sample). The session relaunches if MCP is dead.
                result = await session.send(
                    sent_prompt,
                    log_label=(
                        f"[{self._current_sample_id}] answer batch "
                        f"{batch_no}/{total_batches} (attempt {attempt + 1})"
                    ),
                )
                parsed = (
                    [strip_reasoning_scaffold(result.text).strip()]
                    if self._raw_prompt
                    else parse_batch_response(result.text, n)
                )
                last_exc = None
            except Exception as e:
                last_exc = e
                result = None
                parsed = [""] * n
                logger.warning(
                    "pam_mcp harness run failed for batch %d/%d (%d questions), attempt %d/%d: %r",
                    batch_no,
                    total_batches,
                    n,
                    attempt + 1,
                    attempts_total,
                    e,
                )
            answered = sum(1 for a in parsed if a)
            # `num_turns >= 2` means at least one tool round-trip happened (turn 1
            # = assistant tool_use, turn 2 = answer after the tool result); a
            # single-turn reply answered from nothing without retrieving. Require a
            # retrieval unless this was the last attempt, so we never score an
            # answer the agent produced without touching PAM Memory.
            retrieved = result is not None and result.num_turns >= 2
            if answered > 0 and (retrieved or attempt == attempts_total - 1):
                break
            if answered > 0 and not retrieved:
                logger.warning(
                    "pam_mcp batch %d/%d answered without calling %s "
                    "(num_turns=%s); retrying to force retrieval",
                    batch_no,
                    total_batches,
                    self.MCP_TOOL,
                    result.num_turns if result is not None else None,
                )
        return result, parsed, answered, last_exc

    def _single_response(
        self,
        result: HarnessResult | None,
        answer: str,
        rendered: str,
        last_exc: Exception | None,
    ) -> BaselineResponse:
        """Build one BaselineResponse from a single-question harness result."""
        prompt_tok_total = count_tokens(self._harness_model, rendered)
        if result is None:
            raw = {"raw_prompt": rendered, "raw_response": f"<harness run failed: {last_exc!r}>"}
            return self._empty_response(0.0, raw=raw, prompt_tokens=prompt_tok_total)
        total_input = result.input_tokens + result.cache_read_tokens + result.cache_write_tokens
        prompt_tok, context_tok = split_input_tokens(total_input, prompt_tok_total)
        return BaselineResponse(
            text=answer,
            usage=TokenUsage(
                input_tokens=total_input,
                output_tokens=result.output_tokens,
                prompt_tokens=prompt_tok,
                context_tokens=context_tok,
                est_cost_usd=result.cost_usd,
                injected_tokens=None,
                enriched_user_prompt_tokens=None,
                agent_input_tokens=result.input_tokens,
                agent_output_tokens=result.output_tokens,
                agent_cache_read_tokens=result.cache_read_tokens,
                agent_cache_write_tokens=result.cache_write_tokens,
            ),
            latency_ms=result.duration_ms,
            raw={"raw_prompt": rendered, "raw_response": result.text},
        )

    async def answer_samples(self, prompt: str) -> list[BaselineResponse]:
        """avg@k: K independent responses for ONE question, generated in parallel.

        Raw mode only. Fans the same mandatory-retrieval prompt to all K pool
        sessions concurrently and returns only once every one is back (per-question
        barrier). Each session keeps its own history → K parallel trajectories.
        """
        assert self._raw_prompt, "answer_samples requires raw_prompt mode"
        assert self._scratch_dir is not None
        self._batch_index += 1
        batch_no = self._batch_index
        total_batches = self._total_batches or batch_no

        # Space out questions within a sample (no sleep before the first one).
        if batch_no > 1 and self.INTER_BATCH_SLEEP_SEC > 0:
            await asyncio.sleep(self.INTER_BATCH_SLEEP_SEC)

        rendered = prompt
        base_prompt = prompts.raw_answer_prompt(prompt, tool_name=self.MCP_TOOL)
        k = len(self._sessions)
        logger.info(
            "pam_mcp: asking question %d/%d with k=%d samples for sample=%s via MCP — waiting...",
            batch_no,
            total_batches,
            k,
            self._current_sample_id,
        )

        async def _one(session: Any) -> BaselineResponse:
            result, parsed, _answered, last_exc = await self._run_attempts(
                session, base_prompt, batch_no=batch_no, total_batches=total_batches, n=1
            )
            if result is not None:
                self._record_session(result)
            return self._single_response(result, parsed[0] if parsed else "", rendered, last_exc)

        # Barrier: all K in parallel; return only when every one has finished.
        responses = await asyncio.gather(*(_one(s) for s in self._sessions))
        answered = sum(1 for r in responses if (r.text or "").strip())
        logger.info(
            "pam_mcp answered %d/%d samples for question %d/%d sample=%s",
            answered,
            k,
            batch_no,
            total_batches,
            self._current_sample_id,
        )
        return list(responses)

    async def answer_batch(self, prompts_list: list[str]) -> list[BaselineResponse]:
        if not prompts_list:
            return []
        assert self._scratch_dir is not None

        n = len(prompts_list)
        if self._raw_prompt:
            # Raw mode: one question at a time, no numbered-batch answer
            # scaffolding. `rendered` stays the bare question (for token counting
            # and the responses.log record), but the prompt actually sent wraps it
            # with a mandatory-retrieval directive — the soft MCP system prompt
            # alone let the agent answer without ever calling the tool.
            assert n == 1, "raw_prompt mode requires batch_size=1"
            rendered = prompts_list[0]
            base_prompt = prompts.raw_answer_prompt(prompts_list[0], tool_name=self.MCP_TOOL)
        else:
            rendered = render_batch_prompt(prompts_list)
            base_prompt = prompts.answer_prompt(rendered, tool_name=self.MCP_TOOL)
        self._batch_index += 1
        batch_no = self._batch_index
        total_batches = self._total_batches or batch_no

        # Space out batches within a sample (no sleep before the first one).
        if batch_no > 1 and self.INTER_BATCH_SLEEP_SEC > 0:
            await asyncio.sleep(self.INTER_BATCH_SLEEP_SEC)

        # prompt_tokens = tokens of the prompt we send (harness tokenizer),
        # split evenly across the batch's questions.
        prompt_share = distribute(count_tokens(self._harness_model, rendered), n)

        logger.info(
            "pam_mcp: asking batch %d/%d (%d questions) for sample=%s via MCP — waiting...",
            batch_no,
            total_batches,
            n,
            self._current_sample_id,
        )

        # Run the harness on the first pool session; retry on empty/no-retrieval.
        result, parsed, answered, last_exc = await self._run_attempts(
            self._sessions[0], base_prompt, batch_no=batch_no, total_batches=total_batches, n=n
        )

        if result is None and last_exc is not None:
            raw = {"raw_prompt": rendered, "raw_response": f"<harness run failed: {last_exc!r}>"}
            return [
                self._empty_response(0.0, raw=raw, prompt_tokens=prompt_share[i]) for i in range(n)
            ]

        assert result is not None
        self._record_session(result)
        logger.info(
            "pam_mcp answered %d/%d questions in batch %d/%d for sample=%s (%.0f ms, cost=$%.4f)",
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
                "pam_mcp batch %d/%d reply missing answers for slots %s (batch size=%d)",
                batch_no,
                total_batches,
                missing,
                n,
            )

        # Distribute the single batch run's usage across the questions (same as
        # McpHarnessBaseline). input_tokens = fresh + cache-read + cache-write.
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
                        # injected/enriched are Pam-chat concepts; N/A here.
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
        # Close the per-conversation session first (it holds the live claude
        # process + the temp MCP config that lives under the scratch dir).
        await self._close_sessions()
        # Wipe the per-sample scratch dir (just held the temp MCP config).
        if self._scratch_dir is not None:
            await asyncio.to_thread(shutil.rmtree, self._scratch_dir.parent, True)

        if self._debug_user_id is not None:
            logger.info("pam_mcp debug mode: skipping delete_account")
            return
        if self._backup_memory:
            # Keep the whole account (and its built memory) for reuse later via
            # --pam-debug-user-id. Nothing is deleted.
            logger.info(
                "pam_mcp backup mode: preserving user_id=%s (account NOT deleted)",
                self._pam_user_id,
            )
            return
        uid = self._pam_user_id
        if uid is None:
            return
        try:
            await asyncio.to_thread(self.client.delete_account, user_id=uid)
            logger.info("pam_mcp deleted user_id=%s", uid)
        except Exception as e:
            logger.warning("pam_mcp delete_account failed for user_id=%s: %r", uid, e)

    async def teardown(self) -> None:
        await self._close_sessions()  # defensive: normally closed in cleanup_sample
        await self.harness.teardown()

    def extras(self) -> dict[str, Any]:
        return {
            "memory_creation_duration_sec": self._memory_creation_sec,
            "pam_user_id": self._pam_user_id,
            "harness": self.harness.name,
            "harness_model": self._harness_model,
            "batch_size": self.batch_size,
            "raw_prompt": self._raw_prompt,
            "pam_memory_run_ids": list(self._last_memory_run_ids),
            "harness_session_ids": list(self._session_ids),
            "mcp_url": self._mcp_url,
            "mcp_key_prefix": self._mcp_key_prefix,
        }

    def baseline_kwargs_extra(self) -> dict[str, Any]:
        return {
            "harness": self.harness.name,
            "harness_model": self._harness_model,
        }

    # ----- helpers --------------------------------------------------------

    def _record_session(self, result: HarnessResult) -> None:
        if result.session_id:
            self._session_ids.append(result.session_id)

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
                injected_tokens=None,
                enriched_user_prompt_tokens=None,
            ),
            latency_ms=latency_ms,
            raw=raw or {},
        )
