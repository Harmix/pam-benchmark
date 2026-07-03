"""PamMcpBaseline driven by the LoCoMo pipeline against a stub PamClient + fake
harness.

Asserts: the per-sample lifecycle (server-side memory build via Pam, then
answering through the harness + PAM Memory MCP), that the MCP config / system
prompt / allowed tools reach the harness, token mapping, 0/N retry, and the
--backup-memory / --pam-debug-user-id account-lifecycle knobs.
"""

from __future__ import annotations

import asyncio
from itertools import count
from typing import Any

import pytest

from baselines.pam_mcp import baseline as pam_mcp_mod
from baselines.pam_mcp.baseline import PamMcpBaseline
from baselines.pam_mcp.prompts import SYSTEM_PROMPT
from datasets.locomo.schemas import LoCoMoQA, LoCoMoSample
from tasks.locomo.pipeline import run_sample


class StubPamClient:
    """Records every call and returns canned Pam responses for `pam_mcp`."""

    def __init__(self, host: str, api_key: str | None = None):
        self.host = host
        self.base_url = f"{host.rstrip('/')}/v1"
        self.api_key = api_key
        self.user_id: int | None = None
        self.admin_token: str | None = None
        self.access_token: str | None = None
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._next_user_id = count(12345)

    def _log(self, method: str, **kwargs: Any) -> None:
        self.calls.append((method, kwargs))

    def login(self, email: str, password: str) -> str:
        self._log("login", email=email)
        self.admin_token = "admin-token"
        return self.admin_token

    def create_account(self, **kwargs: Any) -> dict[str, Any]:
        self._log("create_account", **kwargs)
        self.user_id = next(self._next_user_id)
        self.access_token = f"user-{self.user_id}-token"
        return {"user": {"id": self.user_id}, "tokens": {"access_token": self.access_token}}

    def process_generic_files(self, files: list[tuple[str, bytes]]) -> list[str]:
        run_id = f"run-{self.user_id}-0"
        self._log(
            "process_generic_files",
            n_files=len(files),
            names=[f[0] for f in files],
            for_user_id=self.user_id,
            run_id=run_id,
        )
        return [run_id]

    def wait_for_memory(self, run_ids: list[str], user_id: int | None = None) -> None:
        uid = user_id if user_id is not None else self.user_id
        self._log("wait_for_memory", run_ids=list(run_ids), user_id=uid)

    def rotate_developer_key(self) -> str:
        key = f"pam_mkey_uid{self.user_id}.secret-xyz"
        self._log("rotate_developer_key", for_user_id=self.user_id, key=key)
        return key

    def issue_user_tokens(self, user_id: int) -> str:
        self.user_id = user_id
        self.access_token = f"user-{user_id}-minted-token"
        self._log("issue_user_tokens", user_id=user_id)
        return self.access_token

    def delete_account(self, user_id: int | None = None) -> None:
        uid = user_id if user_id is not None else self.user_id
        self._log("delete_account", user_id=uid)


def _sample(n: int) -> LoCoMoSample:
    qa = [LoCoMoQA(question=f"q-{i}", answer=f"a-{i}", category=1) for i in range(1, n + 1)]
    return LoCoMoSample(
        sample_id="conv-x",
        qa=qa,
        conversation={
            "speaker_a": "Alice",
            "speaker_b": "Bob",
            "session_1_date_time": "1 Jan 2024",
            "session_1": [{"speaker": "Alice", "dia_id": "D1:1", "text": "hi there"}],
        },
    )


def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAM_API_HOST", "https://staging.api.pam.harmix.ai")
    monkeypatch.setenv("PAM_API_USER", "admin@stub")
    monkeypatch.setenv("PAM_API_PASSWORD", "stub-password")
    monkeypatch.setenv("PAM_API_KEY", "harmix-key")


def _baseline(monkeypatch, tmp_path, fake_harness_factory, **kw) -> PamMcpBaseline:
    _set_env(monkeypatch)
    monkeypatch.setattr(pam_mcp_mod, "PamClient", StubPamClient)
    return PamMcpBaseline(
        harness=fake_harness_factory(model="gpt-4o", script=kw.pop("script", None)),
        harness_model="gpt-4o",
        output_root=tmp_path / "out",
        **kw,
    )


def test_lifecycle_call_order_and_mcp_wiring(monkeypatch, tmp_path, fake_harness_factory):
    baseline = _baseline(monkeypatch, tmp_path, fake_harness_factory, batch_size=10)
    sample = _sample(12)

    async def _go():
        await baseline.setup(seed=42)
        preds = await run_sample(sample, baseline=baseline, seed=42, model_name="pam_mcp")
        await baseline.teardown()
        return preds

    preds = asyncio.run(_go())

    methods = [c[0] for c in baseline.client.calls]
    assert methods == [
        "login",
        "create_account",
        "process_generic_files",
        "wait_for_memory",
        "rotate_developer_key",
        "delete_account",
    ]
    # The account is created on the MCP-only `dev` plan (which grants MEMORY_MCP).
    create_call = next(c for c in baseline.client.calls if c[0] == "create_account")
    assert create_call[1]["plan"] == "dev"

    # 12 questions / batch 10 → 2 harness answer calls.
    assert baseline.harness.answer_calls == 2
    call = baseline.harness.calls[0]
    assert call["allowed_tools"] == [PamMcpBaseline.MCP_TOOL]
    assert call["system"] == SYSTEM_PROMPT
    server = call["mcp_servers"]["pam_memory"]
    assert server["type"] == "http"
    assert server["url"] == "https://staging.api.pam.harmix.ai/v1/mcp/memory"
    # The rotated key flows verbatim into the Authorization header.
    assert server["headers"]["Authorization"] == "pam_mkey_uid12345.secret-xyz"

    assert [p.model_answer for p in preds[:3]] == ["ans-1", "ans-2", "ans-3"]
    # extras only ever exposes the non-secret key prefix.
    extras = baseline.extras()
    assert extras["mcp_key_prefix"] == "pam_mkey_uid12345"
    assert extras["pam_user_id"] == 12345
    assert extras["pam_memory_run_ids"] == ["run-12345-0"]


def test_token_mapping(monkeypatch, tmp_path, fake_harness_factory):
    baseline = _baseline(monkeypatch, tmp_path, fake_harness_factory, batch_size=4)

    async def _go():
        await baseline.setup(seed=1)
        return await run_sample(_sample(4), baseline=baseline, seed=1, model_name="pam_mcp")

    preds = asyncio.run(_go())
    # input = fresh(400)+cache_read(40)+cache_write(20)=460 → 115/q; fresh 400/4=100.
    assert [p.input_tokens for p in preds] == [115, 115, 115, 115]
    assert [p.agent_input_tokens for p in preds] == [100, 100, 100, 100]
    assert [p.output_tokens for p in preds] == [50, 50, 50, 50]
    assert [p.agent_cache_read_tokens for p in preds] == [10, 10, 10, 10]
    assert [p.agent_cache_write_tokens for p in preds] == [5, 5, 5, 5]
    assert all(abs(p.est_cost_usd - 0.2) < 1e-9 for p in preds)
    assert all(abs(p.latency_ms - 250.0) < 1e-9 for p in preds)
    # injected/enriched are N/A for a harness-answered baseline.
    assert all(p.injected_tokens is None for p in preds)
    assert all(p.enriched_user_prompt_tokens is None for p in preds)


def test_zero_answers_retries_twice_then_gives_up(monkeypatch, tmp_path, fake_harness_factory):
    baseline = _baseline(monkeypatch, tmp_path, fake_harness_factory, batch_size=3, script=[""])

    async def _go():
        await baseline.setup(seed=1)
        return await run_sample(_sample(3), baseline=baseline, seed=1, model_name="pam_mcp")

    preds = asyncio.run(_go())
    assert baseline.harness.answer_calls == 3  # 1 original + 2 retries
    assert all(p.model_answer == "" for p in preds)


def test_zero_answers_recovers_on_retry(monkeypatch, tmp_path, fake_harness_factory):
    full = "\n".join(f"A{i}: got-{i}" for i in range(1, 4))
    baseline = _baseline(
        monkeypatch, tmp_path, fake_harness_factory, batch_size=3, script=["", full]
    )

    async def _go():
        await baseline.setup(seed=1)
        return await run_sample(_sample(3), baseline=baseline, seed=1, model_name="pam_mcp")

    preds = asyncio.run(_go())
    assert baseline.harness.answer_calls == 2
    assert [p.model_answer for p in preds] == ["got-1", "got-2", "got-3"]


def test_answer_without_retrieval_retries_then_accepts(monkeypatch, tmp_path, fake_harness_factory):
    """A reply that never called the tool (num_turns<2) is retried up to the cap
    to force a retrieval; the final attempt's answers are still accepted."""
    baseline = _baseline(monkeypatch, tmp_path, fake_harness_factory, batch_size=3)
    # Non-empty answers but no tool round-trip on every attempt.
    baseline.harness.usage["num_turns"] = 1

    async def _go():
        await baseline.setup(seed=1)
        return await run_sample(_sample(3), baseline=baseline, seed=1, model_name="pam_mcp")

    preds = asyncio.run(_go())
    assert baseline.harness.answer_calls == 3  # 1 original + 2 retries to force retrieval
    assert all(p.model_answer for p in preds)  # last attempt's answers still accepted


def test_backup_memory_skips_delete(monkeypatch, tmp_path, fake_harness_factory):
    baseline = _baseline(
        monkeypatch, tmp_path, fake_harness_factory, batch_size=1, backup_memory=True
    )

    async def _go():
        await baseline.setup(seed=1)
        await run_sample(_sample(1), baseline=baseline, seed=1, model_name="pam_mcp")
        await baseline.teardown()

    asyncio.run(_go())
    methods = [c[0] for c in baseline.client.calls]
    assert "create_account" in methods
    assert "rotate_developer_key" in methods
    assert "delete_account" not in methods


def test_debug_user_id_reuses_account(monkeypatch, tmp_path, fake_harness_factory):
    baseline = _baseline(
        monkeypatch, tmp_path, fake_harness_factory, batch_size=5, debug_user_id=999
    )

    async def _go():
        await baseline.setup(seed=1)
        await run_sample(_sample(5), baseline=baseline, seed=1, model_name="pam_mcp")
        await baseline.teardown()

    asyncio.run(_go())
    methods = [c[0] for c in baseline.client.calls]
    # Reuse: mint per-user token → rotate key → answer. No create/upload/build
    # and no delete (the reused account already has the dev-plan MEMORY_MCP flag).
    assert methods == [
        "login",
        "issue_user_tokens",
        "rotate_developer_key",
    ]
    assert baseline.client.user_id == 999
    assert baseline.harness.answer_calls == 1
