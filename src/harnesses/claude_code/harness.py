"""Claude Code harness — drives the official `claude` CLI headlessly.

One `run()` == one `claude -p "<prompt>" --output-format json ...` invocation in
a given working directory, returning the result text plus real token/cost usage
parsed from the JSON output. Auth is Vertex AI (see `auth.vertex_env`).

NOTE: the exact CLI flag names below should be confirmed against the installed
`claude --help` during the M0 spike (see docs/mcp_harness_benchmark_plan.md);
they are centralized here so a change is a one-line edit.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import signal
import tempfile
from pathlib import Path
from typing import Any

from harnesses.base import HarnessResult

from .auth import vertex_env

logger = logging.getLogger(__name__)


class ClaudeCodeHarness:
    """Headless Claude Code runtime (CLI subprocess, Vertex AI auth)."""

    name = "claude-code"

    # Default non-interactive permission mode. We always pass an explicit
    # --allowedTools allowlist, so edits/reads inside the working dir are
    # auto-approved without prompting.
    DEFAULT_PERMISSION_MODE = "acceptEdits"
    DEFAULT_TIMEOUT_SEC = 600.0

    # HTTP MCP servers connect asynchronously at startup. With a short startup
    # timeout a slow handshake (e.g. the dev PAM Memory server) times out and the
    # server never registers, so every `mcp__…` tool call in that process fails
    # with "No such tool available". A generous default lets the connection
    # complete; overridable via the MCP_TIMEOUT env var. (ms)
    MCP_STARTUP_TIMEOUT_MS = 60000
    # If a required MCP tool is dead for a whole invocation (every call returned
    # "No such tool available"), retry the invocation — a fresh process reconnects.
    MCP_CONNECT_RETRIES = 2
    MCP_CONNECT_RETRY_SLEEP_SEC = 3.0
    # In a persistent session, pause after launch before the first message so the
    # async MCP handshake completes instead of the model racing ahead of it.
    MCP_CONNECT_SETTLE_SEC = 3.0

    def __init__(
        self,
        model: str | None = None,
        *,
        cli_path: str = "claude",
        permission_mode: str | None = None,
        max_turns: int | None = None,
    ) -> None:
        self.model = model
        self._cli = cli_path
        self._permission_mode = permission_mode or self.DEFAULT_PERMISSION_MODE
        self._default_max_turns = max_turns
        self._env: dict[str, str] | None = None

    async def setup(self) -> None:
        # Resolve Vertex env once (this also downloads gs:// credentials if used).
        self._env = await asyncio.to_thread(vertex_env)

    async def teardown(self) -> None:
        return None

    def _build_argv(
        self,
        *,
        prompt: str,
        allowed_tools: list[str] | None,
        mcp_config_path: str | None,
        system: str | None,
        max_turns: int | None,
        capture_logs: bool = False,
    ) -> list[str]:
        # `stream-json` (+ required `--verbose`) emits the full turn-by-turn
        # transcript — system init, assistant messages with thinking and
        # tool_use blocks, tool results, and the final result event — which we
        # persist for the --save-responses debug log. Plain `json` emits only the
        # final result object.
        if capture_logs:
            argv = [self._cli, "-p", prompt, "--output-format", "stream-json", "--verbose"]
        else:
            argv = [self._cli, "-p", prompt, "--output-format", "json"]
        argv += ["--permission-mode", self._permission_mode]
        if self.model:
            argv += ["--model", self.model]
        if allowed_tools:
            argv += ["--allowedTools", ",".join(allowed_tools)]
        if mcp_config_path:
            argv += ["--mcp-config", mcp_config_path, "--strict-mcp-config"]
        if system:
            argv += ["--append-system-prompt", system]
        effective_turns = max_turns if max_turns is not None else self._default_max_turns
        if effective_turns is not None:
            argv += ["--max-turns", str(effective_turns)]
        return argv

    def _build_session_argv(
        self,
        *,
        allowed_tools: list[str] | None,
        mcp_config_path: str | None,
        system: str | None,
        max_turns: int | None,
    ) -> list[str]:
        """argv for a persistent streaming session (`--input-format stream-json`).

        The process stays alive and reads newline-delimited user messages from
        stdin, so MCP servers connect ONCE at startup and every subsequent batch
        reuses that connection (no per-batch handshake, no reconnection race).
        There is no positional prompt — turns arrive over stdin.
        """
        argv = [
            self._cli,
            "-p",
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--verbose",
            "--permission-mode",
            self._permission_mode,
        ]
        if self.model:
            argv += ["--model", self.model]
        if allowed_tools:
            argv += ["--allowedTools", ",".join(allowed_tools)]
        if mcp_config_path:
            argv += ["--mcp-config", mcp_config_path, "--strict-mcp-config"]
        if system:
            argv += ["--append-system-prompt", system]
        effective_turns = max_turns if max_turns is not None else self._default_max_turns
        if effective_turns is not None:
            argv += ["--max-turns", str(effective_turns)]
        return argv

    def open_session(
        self,
        *,
        working_dir: Path,
        allowed_tools: list[str] | None = None,
        mcp_servers: dict[str, Any] | None = None,
        system: str | None = None,
        max_turns: int | None = None,
        log_path: Path | None = None,
    ) -> ClaudeCodeSession:
        """Open a persistent Claude Code session (one process, MCP connected once).

        Intended lifetime = one LoCoMo conversation: open in `prepare_for_sample`,
        `send()` one message per batch, `aclose()` in `cleanup_sample`. The
        subprocess launches lazily on the first `send()`.
        """
        return ClaudeCodeSession(
            harness=self,
            working_dir=working_dir,
            allowed_tools=allowed_tools,
            mcp_servers=mcp_servers,
            system=system,
            max_turns=max_turns,
            log_path=log_path,
        )

    async def run(
        self,
        *,
        prompt: str,
        working_dir: Path,
        allowed_tools: list[str] | None = None,
        mcp_servers: dict[str, Any] | None = None,
        system: str | None = None,
        max_turns: int | None = None,
        timeout_sec: float | None = None,
        log_path: Path | None = None,
        log_label: str | None = None,
    ) -> HarnessResult:
        if self._env is None:
            await self.setup()
        working_dir.mkdir(parents=True, exist_ok=True)

        mcp_config_path: str | None = None
        tmp_mcp: str | None = None
        if mcp_servers:
            fd, tmp_mcp = tempfile.mkstemp(prefix="mcp_", suffix=".json", dir=working_dir)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"mcpServers": mcp_servers}, fh)
            mcp_config_path = tmp_mcp

        # Requiring an MCP tool → capture the event stream (stream-json) even
        # when not logging, so we can tell whether the server ever connected.
        mcp_tools = [t for t in (allowed_tools or []) if t.startswith("mcp__")]
        argv = self._build_argv(
            prompt=prompt,
            allowed_tools=allowed_tools,
            mcp_config_path=mcp_config_path,
            system=system,
            max_turns=max_turns,
            capture_logs=log_path is not None or bool(mcp_tools),
        )
        env = {**os.environ, **(self._env or {})}
        env.setdefault("MCP_TIMEOUT", str(self.MCP_STARTUP_TIMEOUT_MS))

        loop = asyncio.get_running_loop()
        t0 = loop.time()
        attempts = self.MCP_CONNECT_RETRIES + 1 if mcp_tools else 1
        out_text = ""
        err_text = ""
        returncode: int | None = None
        try:
            for attempt in range(attempts):
                proc = await asyncio.create_subprocess_exec(
                    *argv,
                    cwd=str(working_dir),
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout_sec or self.DEFAULT_TIMEOUT_SEC
                )
                returncode = proc.returncode
                out_text = stdout.decode("utf-8", "replace")
                err_text = stderr.decode("utf-8", "replace")
                if log_path is not None:
                    _append_run_log(
                        log_path,
                        label=f"{log_label} [try {attempt + 1}/{attempts}]" if log_label else None,
                        argv=argv,
                        returncode=returncode,
                        out_text=out_text,
                        err_text=err_text,
                    )
                dead_tool = _dead_mcp_tool(out_text, mcp_tools) if returncode == 0 else None
                if dead_tool is not None and attempt < attempts - 1:
                    logger.warning(
                        "claude: MCP tool %r never connected (every call returned "
                        "'No such tool available'); retrying invocation %d/%d",
                        dead_tool,
                        attempt + 1,
                        self.MCP_CONNECT_RETRIES,
                    )
                    await asyncio.sleep(self.MCP_CONNECT_RETRY_SLEEP_SEC)
                    continue
                break
        finally:
            if tmp_mcp:
                Path(tmp_mcp).unlink(missing_ok=True)
        wall_ms = (loop.time() - t0) * 1000.0

        if returncode != 0:
            # Claude Code usually reports the real error as JSON on stdout (with
            # an empty stderr), so surface both. Pull out a clean message if the
            # stdout is a JSON error result.
            detail = err_text.strip() or out_text.strip()
            data = _last_json_object(out_text)
            if isinstance(data, dict):
                detail = str(data.get("result") or data.get("error") or data) or detail
            shown_argv = [*argv[:2], "<prompt>", *argv[3:]]  # hide the long prompt
            raise RuntimeError(
                f"claude exited {returncode}: {detail[:800]}\nargv: {' '.join(shown_argv)}"
            )

        return self._parse_output(out_text, wall_ms)

    @staticmethod
    def _parse_output(stdout: str, wall_ms: float) -> HarnessResult:
        """Parse Claude Code's `--output-format json` result into a HarnessResult.

        Tolerant of either a single JSON object or NDJSON (takes the last
        parseable object), and of missing usage keys.
        """
        data = _last_json_object(stdout)
        if data is None:
            raise RuntimeError(f"could not parse claude JSON output: {stdout[:500]!r}")
        if data.get("is_error"):
            raise RuntimeError(f"claude reported error: {data.get('result') or data}")

        usage = data.get("usage") or {}
        duration_ms = data.get("duration_ms")
        if duration_ms is None and data.get("duration_seconds") is not None:
            duration_ms = float(data["duration_seconds"]) * 1000.0
        return HarnessResult(
            text=data.get("result", "") or "",
            input_tokens=int(usage.get("input_tokens", 0) or 0),
            output_tokens=int(usage.get("output_tokens", 0) or 0),
            cache_read_tokens=int(usage.get("cache_read_input_tokens", 0) or 0),
            cache_write_tokens=int(usage.get("cache_creation_input_tokens", 0) or 0),
            cost_usd=float(data.get("total_cost_usd", 0.0) or 0.0),
            duration_ms=float(duration_ms if duration_ms is not None else wall_ms),
            session_id=data.get("session_id"),
            num_turns=int(data.get("num_turns", 0) or 0),
            raw=data,
        )


class ClaudeCodeSession:
    """A long-lived `claude` process driven over stream-json stdin/stdout.

    One session == one LoCoMo conversation. The subprocess launches lazily on the
    first `send()`, connects its MCP servers ONCE, and then answers each batch as
    a separate user turn — so the per-batch MCP handshake (and its connection
    race) happens at most once per conversation instead of once per batch. If the
    MCP tool fails to register on startup, `send()` relaunches the process (a
    fresh connection) up to `MCP_CONNECT_RETRIES` times before giving up.
    """

    # 64 MiB line buffer: stream-json tool_result lines (retrieved memory) can be
    # far larger than asyncio's 64 KiB default, which would raise LimitOverrunError.
    _STREAM_LIMIT = 64 * 1024 * 1024

    def __init__(
        self,
        *,
        harness: ClaudeCodeHarness,
        working_dir: Path,
        allowed_tools: list[str] | None,
        mcp_servers: dict[str, Any] | None,
        system: str | None,
        max_turns: int | None,
        log_path: Path | None,
    ) -> None:
        self._h = harness
        self._working_dir = Path(working_dir)
        self._allowed_tools = allowed_tools
        self._mcp_servers = mcp_servers
        self._system = system
        self._max_turns = max_turns
        self._log_path = log_path
        self._mcp_tools = [t for t in (allowed_tools or []) if t.startswith("mcp__")]
        self._mcp_config_path: str | None = None
        self._argv: list[str] = []
        self._proc: asyncio.subprocess.Process | None = None
        self._stderr_task: asyncio.Task | None = None
        self._stderr_buf: list[str] = []

    async def _launch(self) -> None:
        if self._h._env is None:
            await self._h.setup()
        self._working_dir.mkdir(parents=True, exist_ok=True)
        if self._mcp_servers and self._mcp_config_path is None:
            fd, path = tempfile.mkstemp(prefix="mcp_", suffix=".json", dir=self._working_dir)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"mcpServers": self._mcp_servers}, fh)
            self._mcp_config_path = path
        self._argv = self._h._build_session_argv(
            allowed_tools=self._allowed_tools,
            mcp_config_path=self._mcp_config_path,
            system=self._system,
            max_turns=self._max_turns,
        )
        env = {**os.environ, **(self._h._env or {})}
        env.setdefault("MCP_TIMEOUT", str(self._h.MCP_STARTUP_TIMEOUT_MS))
        self._proc = await asyncio.create_subprocess_exec(
            *self._argv,
            cwd=str(self._working_dir),
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=self._STREAM_LIMIT,
            start_new_session=True,  # own process group → kill claude + its children
        )
        self._stderr_buf = []
        self._stderr_task = asyncio.create_task(self._drain_stderr(self._proc))
        # Let the async MCP handshake finish before the first turn races ahead.
        if self._mcp_tools and self._h.MCP_CONNECT_SETTLE_SEC > 0:
            await asyncio.sleep(self._h.MCP_CONNECT_SETTLE_SEC)

    async def _drain_stderr(self, proc: asyncio.subprocess.Process) -> None:
        assert proc.stderr is not None
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            self._stderr_buf.append(line.decode("utf-8", "replace"))

    async def _kill(self) -> None:
        proc, self._proc = self._proc, None
        task, self._stderr_task = self._stderr_task, None
        if proc is not None and proc.returncode is None:
            if proc.stdin is not None and not proc.stdin.is_closing():
                proc.stdin.close()
            self._signal_group(proc, signal.SIGTERM)
            try:
                await asyncio.wait_for(proc.wait(), timeout=10)
            except (TimeoutError, ProcessLookupError):
                self._signal_group(proc, signal.SIGKILL)
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    @staticmethod
    def _signal_group(proc: asyncio.subprocess.Process, sig: int) -> None:
        """Signal the whole process group (claude + its MCP/helper children)."""
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(os.getpgid(proc.pid), sig)

    async def _one_turn(self, prompt: str, timeout_sec: float) -> tuple[str, float]:
        """Send one user message; collect the stream until the `result` event."""
        assert self._proc is not None and self._proc.stdin and self._proc.stdout
        loop = asyncio.get_running_loop()
        t0 = loop.time()
        msg = json.dumps({"type": "user", "message": {"role": "user", "content": prompt}})
        self._proc.stdin.write((msg + "\n").encode("utf-8"))
        await self._proc.stdin.drain()

        lines: list[str] = []
        end = t0 + timeout_sec
        while True:
            remaining = end - loop.time()
            if remaining <= 0:
                raise TimeoutError("claude session turn timed out")
            raw = await asyncio.wait_for(self._proc.stdout.readline(), timeout=remaining)
            if not raw:
                raise RuntimeError("claude session stdout closed (process exited)")
            line = raw.decode("utf-8", "replace")
            lines.append(line)
            s = line.strip()
            if not s.startswith("{"):
                continue
            try:
                obj = json.loads(s)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and obj.get("type") == "result":
                break
        return "".join(lines), (loop.time() - t0) * 1000.0

    async def send(
        self,
        prompt: str,
        *,
        log_label: str | None = None,
        timeout_sec: float | None = None,
    ) -> HarnessResult:
        """Answer one batch on the persistent session, relaunching if MCP is dead."""
        retries = self._h.MCP_CONNECT_RETRIES if self._mcp_tools else 0
        turn_timeout = timeout_sec or self._h.DEFAULT_TIMEOUT_SEC
        out_text = ""
        wall_ms = 0.0
        for attempt in range(retries + 1):
            if self._proc is None or self._proc.returncode is not None:
                await self._launch()
            try:
                out_text, wall_ms = await self._one_turn(prompt, turn_timeout)
            except (TimeoutError, RuntimeError) as e:
                await self._kill()
                if attempt < retries:
                    logger.warning(
                        "claude session turn failed (%r); relaunching session %d/%d",
                        e,
                        attempt + 1,
                        retries,
                    )
                    await asyncio.sleep(self._h.MCP_CONNECT_RETRY_SLEEP_SEC)
                    continue
                raise
            if self._log_path is not None:
                _append_run_log(
                    self._log_path,
                    label=f"{log_label} [try {attempt + 1}/{retries + 1}]" if log_label else None,
                    argv=self._argv,
                    returncode=0,
                    out_text=out_text,
                    err_text="".join(self._stderr_buf),
                )
            dead_tool = _dead_mcp_tool(out_text, self._mcp_tools)
            if dead_tool is not None and attempt < retries:
                logger.warning(
                    "claude session: MCP tool %r never connected (every call "
                    "returned 'No such tool available'); relaunching session %d/%d",
                    dead_tool,
                    attempt + 1,
                    retries,
                )
                await self._kill()  # fresh process → fresh MCP connection
                await asyncio.sleep(self._h.MCP_CONNECT_RETRY_SLEEP_SEC)
                continue
            break
        return self._h._parse_output(out_text, wall_ms)

    async def aclose(self) -> None:
        await self._kill()
        if self._mcp_config_path:
            Path(self._mcp_config_path).unlink(missing_ok=True)
            self._mcp_config_path = None


def _dead_mcp_tool(out_text: str, mcp_tools: list[str]) -> str | None:
    """Return a required MCP tool that was called but NEVER connected.

    Scans the stream-json transcript: a tool is "dead" when it was invoked at
    least once and EVERY invocation came back "No such tool available" (the
    server never registered). If any call succeeded (server connected mid-run),
    the tool is considered healthy and None is returned for it. Returns the first
    dead tool, or None when all required tools connected (or none were used).
    """
    if not mcp_tools:
        return None
    calls = {t: 0 for t in mcp_tools}
    unavailable = {t: 0 for t in mcp_tools}
    id_to_name: dict[str, str] = {}
    for line in out_text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = obj.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for blk in content:
            if not isinstance(blk, dict):
                continue
            if blk.get("type") == "tool_use" and blk.get("name") in calls:
                calls[blk["name"]] += 1
                if blk.get("id"):
                    id_to_name[blk["id"]] = blk["name"]
            elif blk.get("type") == "tool_result":
                body = blk.get("content")
                text = body if isinstance(body, str) else json.dumps(body)
                if "No such tool available" not in text:
                    continue
                name = id_to_name.get(blk.get("tool_use_id", ""))
                if name in unavailable:
                    unavailable[name] += 1
                else:  # unmapped id — attribute by the tool named in the error
                    for t in mcp_tools:
                        if t in text:
                            unavailable[t] += 1
                            break
    for t in mcp_tools:
        if calls[t] > 0 and unavailable[t] >= calls[t]:
            return t
    return None


def _append_run_log(
    log_path: Path,
    *,
    label: str | None,
    argv: list[str],
    returncode: int | None,
    out_text: str,
    err_text: str,
) -> None:
    """Append the full claude-code transcript for one run to `log_path`.

    Writes the raw stream-json events (system init, assistant messages with
    thinking + tool_use, tool results, final result) pretty-printed one per
    block, plus any stderr. Best-effort: logging never breaks a run.
    """
    header = label or "claude-code run"
    shown_argv = [*argv[:2], "<prompt>", *argv[3:]]  # hide the long prompt
    lines = [
        "=" * 78,
        f">>> {header} (returncode={returncode})",
        f"argv: {' '.join(shown_argv)}",
        "=" * 78,
    ]
    for raw_line in out_text.splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            obj = json.loads(raw_line)
        except json.JSONDecodeError:
            lines.append(raw_line)
            continue
        kind = obj.get("type", "event") if isinstance(obj, dict) else "event"
        lines.append(f"--- {kind} ---")
        lines.append(json.dumps(obj, indent=2, ensure_ascii=False))
    if err_text.strip():
        lines.append("--- stderr ---")
        lines.append(err_text.rstrip())
    lines.append("")
    try:
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    except OSError as e:
        logger.warning("failed to write harness log to %s: %r", log_path, e)


def _last_json_object(stdout: str) -> dict[str, Any] | None:
    """Return the last top-level JSON object in `stdout` (single object or NDJSON)."""
    stripped = stdout.strip()
    if not stripped:
        return None
    try:
        obj = json.loads(stripped)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    last: dict[str, Any] | None = None
    for line in stripped.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            last = obj
    return last
