"""Harness abstraction — an agentic runtime we can drive headlessly.

A *harness* is a coding-agent runtime (Claude Code first; Codex / OpenClaw
later) that we invoke with a prompt, a working directory, and a set of allowed
tools / MCP servers, and that returns text plus real token/cost usage. The MCP
memory baselines (`baselines/mcp/`) run *on top of* a harness, so adding a new
harness is a new `Harness` implementation rather than a rewrite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@dataclass
class HarnessResult:
    """One headless agent invocation's result + usage."""

    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    duration_ms: float = 0.0
    session_id: str | None = None
    num_turns: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Harness(Protocol):
    """Contract every agentic runtime implements.

    Lifecycle:
        await harness.setup()
        result = await harness.run(prompt=..., working_dir=..., allowed_tools=[...])
        await harness.teardown()
    """

    name: str  # e.g. "claude-code"
    model: str | None  # base model id for this run (overridable)

    async def setup(self) -> None: ...

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
    ) -> HarnessResult: ...

    async def teardown(self) -> None: ...
