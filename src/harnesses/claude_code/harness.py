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
import json
import logging
import os
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
    ) -> list[str]:
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

        argv = self._build_argv(
            prompt=prompt,
            allowed_tools=allowed_tools,
            mcp_config_path=mcp_config_path,
            system=system,
            max_turns=max_turns,
        )
        env = {**os.environ, **(self._env or {})}

        loop = asyncio.get_running_loop()
        t0 = loop.time()
        try:
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
        finally:
            if tmp_mcp:
                Path(tmp_mcp).unlink(missing_ok=True)
        wall_ms = (loop.time() - t0) * 1000.0

        out_text = stdout.decode("utf-8", "replace")
        err_text = stderr.decode("utf-8", "replace")
        if proc.returncode != 0:
            # Claude Code usually reports the real error as JSON on stdout (with
            # an empty stderr), so surface both. Pull out a clean message if the
            # stdout is a JSON error result.
            detail = err_text.strip() or out_text.strip()
            data = _last_json_object(out_text)
            if isinstance(data, dict):
                detail = str(data.get("result") or data.get("error") or data) or detail
            shown_argv = [*argv[:2], "<prompt>", *argv[3:]]  # hide the long prompt
            raise RuntimeError(
                f"claude exited {proc.returncode}: {detail[:800]}\nargv: {' '.join(shown_argv)}"
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
