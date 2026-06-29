"""Shared fixtures for the `pam_mcp` baseline tests.

A stub `PamClient` (records calls, no network) plus a fake harness that captures
the MCP config / system prompt / allowed tools and returns canned numbered
answers. Sleeps are zeroed so the suite is fast.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from baselines.pam_mcp.baseline import PamMcpBaseline
from harnesses.base import HarnessResult

_Q_LINE = re.compile(r"^Q\d+:", re.MULTILINE)


class FakeHarness:
    """Captures answer calls (MCP config, system, allowed tools); returns canned
    numbered answers. `script` drives successive batches; `""` = a 0/N reply."""

    name = "fake"

    def __init__(self, model: str | None = None, *, script: list[str] | None = None):
        self.model = model
        self.calls: list[dict] = []
        self._script = script or []
        self._idx = 0
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

    async def run(
        self,
        *,
        prompt,
        working_dir,
        allowed_tools=None,
        mcp_servers=None,
        system=None,
        **_kw,
    ) -> HarnessResult:
        Path(working_dir).mkdir(parents=True, exist_ok=True)
        self.calls.append(
            {
                "allowed_tools": allowed_tools,
                "mcp_servers": mcp_servers,
                "system": system,
            }
        )
        n = len(_Q_LINE.findall(prompt))
        if self._idx < len(self._script):
            text = self._script[self._idx]
        elif self._script:
            text = self._script[-1]
        else:
            text = "\n".join(f"A{i}: ans-{i}" for i in range(1, n + 1))
        self._idx += 1
        return HarnessResult(text=text, session_id=f"ans-{self._idx}", **self.usage)

    @property
    def answer_calls(self) -> int:
        return len(self.calls)


@pytest.fixture(autouse=True)
def _no_pam_mcp_sleeps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(PamMcpBaseline, "INTER_BATCH_SLEEP_SEC", 0.0)
    monkeypatch.setattr(PamMcpBaseline, "BATCH_RETRY_BASE_SLEEP_SEC", 0.0)


@pytest.fixture
def fake_harness_factory():
    return FakeHarness
