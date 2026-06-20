"""Shared fixtures for MCP-harness baseline tests — a fake harness (no Claude
Code, no network) and zeroed sleeps so the suite is fast."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from baselines.mcp.base import McpHarnessBaseline
from harnesses.base import HarnessResult

_Q_LINE = re.compile(r"^Q\d+:", re.MULTILINE)


class FakeHarness:
    """Records calls; returns canned ingest/answer results with fixed usage.

    Answer phase is detected by the presence of `Q1:` lines in the prompt. The
    `script` (list of raw answer texts) drives successive answer-batch calls;
    `""` simulates a 0/N (no-answer) reply. Usage values are fixed so token
    mapping can be asserted exactly.
    """

    name = "fake"

    def __init__(self, model: str | None = None, *, script: list[str] | None = None):
        self.model = model
        self.calls: list[dict] = []
        self._script = script or []
        self._answer_idx = 0
        # Fixed per-run usage (batch-level).
        self.usage = dict(
            input_tokens=400,
            output_tokens=200,
            cache_read_tokens=40,
            cache_write_tokens=20,
            cost_usd=0.8,
            duration_ms=1000.0,
        )

    async def setup(self) -> None:
        return None

    async def teardown(self) -> None:
        return None

    async def run(self, *, prompt, working_dir, allowed_tools=None, **_kw) -> HarnessResult:
        Path(working_dir).mkdir(parents=True, exist_ok=True)
        is_answer = bool(_Q_LINE.search(prompt))
        self.calls.append(
            {"phase": "answer" if is_answer else "ingest", "allowed_tools": allowed_tools}
        )
        if not is_answer:
            return HarnessResult(text="MEMORY_WRITTEN", session_id="ingest-sess", **self.usage)

        n = len(_Q_LINE.findall(prompt))
        if self._answer_idx < len(self._script):
            text = self._script[self._answer_idx]
        elif self._script:
            text = self._script[-1]
        else:
            text = "\n".join(f"A{i}: ans-{i}" for i in range(1, n + 1))
        self._answer_idx += 1
        return HarnessResult(text=text, session_id=f"ans-{self._answer_idx}", **self.usage)

    @property
    def answer_calls(self) -> int:
        return sum(1 for c in self.calls if c["phase"] == "answer")


@pytest.fixture(autouse=True)
def _no_mcp_sleeps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(McpHarnessBaseline, "INTER_BATCH_SLEEP_SEC", 0.0)
    monkeypatch.setattr(McpHarnessBaseline, "BATCH_RETRY_BASE_SLEEP_SEC", 0.0)


@pytest.fixture
def fake_harness_factory():
    return FakeHarness
