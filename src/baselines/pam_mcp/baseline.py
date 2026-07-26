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
        # One persistent Claude Code session per conversation: the MCP server
        # connects once here (in prepare_for_sample) and every batch reuses it,
        # instead of re-handshaking (and racing) on every batch.
        self._session: Any = None

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
        await self._open_session()

    async def _open_session(self) -> None:
        """Open the per-conversation Claude Code session (MCP connects once)."""
        await self._close_session()
        assert self._scratch_dir is not None
        self._session = self.harness.open_session(
            working_dir=self._scratch_dir,
            allowed_tools=[self.MCP_TOOL],
            mcp_servers=self._mcp_servers(),
            system=prompts.SYSTEM_PROMPT,
            max_turns=self._max_turns,
            log_path=self._harness_log,
        )

    async def _close_session(self) -> None:
        if self._session is not None:
            try:
                await self._session.aclose()
            finally:
                self._session = None

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

        # Run the harness; retry on a fully-empty (0/N) reply with exp. backoff.
        result: HarnessResult | None = None
        parsed: list[str] = [""] * n
        answered = 0
        last_exc: Exception | None = None
        attempts_total = self._max_batch_retries + 1
        # First attempt sends the base prompt; retries escalate with a firmer
        # "you did NOT retrieve — call the tool now" preamble so the re-send
        # actually forces the tool call instead of re-rolling the same prompt.
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
                assert self._session is not None
                # One turn on the per-conversation session — the MCP server is
                # already connected (from prepare_for_sample), so no per-batch
                # handshake. The session relaunches internally if MCP is dead.
                result = await self._session.send(
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
        await self._close_session()
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
        await self._close_session()  # defensive: normally closed in cleanup_sample
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
