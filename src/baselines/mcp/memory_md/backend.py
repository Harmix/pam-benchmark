"""`memory_md_mcp` backend — markdown filesystem memory via native file tools.

Realization "Option A" (see docs/mcp_harness_benchmark_plan.md): the agent
manages a directory of Obsidian-style Markdown notes with its built-in file
tools (Read/Write/Edit/Grep/Glob). No external MCP server — `mcp_servers`
returns None — so the baseline's correctness is defined entirely by our prompt
protocol (`prompts.py`), which makes it transparent and reproducible.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import ClassVar

from baselines.mcp.memory_md import prompts


class MemoryMdBackend:
    """Markdown filesystem memory backend."""

    name = "memory_md_mcp"

    # Write tools for ingestion; read-only tools for answering (so the answer
    # phase cannot mutate memory, and never re-reads the raw transcript).
    _INGEST_TOOLS: ClassVar[list[str]] = ["Read", "Write", "Edit", "Grep", "Glob", "LS"]
    _ANSWER_TOOLS: ClassVar[list[str]] = ["Read", "Grep", "Glob", "LS"]

    async def setup(self) -> None:
        return None

    def mcp_servers(self, memory_dir: Path) -> dict | None:
        # Native file tools only — no MCP server.
        return None

    def allowed_tools(self, phase: str) -> list[str]:
        return list(self._INGEST_TOOLS if phase == "ingest" else self._ANSWER_TOOLS)

    def ingest_prompt(self, conversation_text: str) -> str:
        return prompts.ingest_prompt(conversation_text)

    def answer_prompt(self, batch_prompt: str) -> str:
        return prompts.answer_prompt(batch_prompt)

    async def reset(self, memory_dir: Path) -> None:
        """Clear any existing memory so the sample starts from an empty store."""
        notes = memory_dir / "notes"
        if notes.exists():
            shutil.rmtree(notes, ignore_errors=True)
        index = memory_dir / "index.md"
        if index.exists():
            index.unlink()

    def memory_exists(self, memory_dir: Path) -> bool:
        """True if a built memory is already present (for debug reuse)."""
        return (memory_dir / "index.md").exists() or (memory_dir / "notes").exists()
