"""Pam agent-side token metrics: message_metrics → per-question distribution."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from itertools import count

from baselines.pam import baseline as pam_baseline_mod
from baselines.pam.baseline import _distribute
from baselines.pam.metrics_db import AgentMetrics
from datasets.locomo.schemas import LoCoMoQA, LoCoMoSample
from tasks.locomo.pipeline import run_sample

# --- _distribute -----------------------------------------------------------


def test_distribute_sums_back_exactly():
    assert _distribute(100, 4) == [25, 25, 25, 25]
    # remainder spread over the first questions, total preserved
    assert _distribute(10, 3) == [4, 3, 3]
    assert sum(_distribute(403, 7)) == 403


def test_distribute_zero_and_edge():
    assert _distribute(0, 5) == [0, 0, 0, 0, 0]
    assert _distribute(7, 0) == []


# --- integration: metrics flow into predictions ----------------------------


class _StubPamClient:
    def __init__(self, host, api_key=None):
        self.host = host
        self.user_id = None
        self.access_token = None

    def login(self, email, password):
        return "admin-token"

    def create_account(self, **kwargs):
        self.user_id = 555
        self.access_token = "user-555-token"
        return {"user": {"id": 555}, "tokens": {"access_token": self.access_token}}

    def process_generic_files(self, files):
        return ["run-555-0"]

    def wait_for_memory(self, run_ids, user_id=None):
        return None

    def send_message(self, prompt, conversation_id=None):
        n = sum(1 for line in prompt.splitlines() if line.startswith("Q"))
        return "\n".join(f"A{i}: stub-{i}" for i in range(1, n + 1)), 0

    def delete_account(self, user_id=None):
        return None


class _FakeReader:
    """Returns a fresh metrics row (new id each call) so the freshness check in
    `_read_agent_metrics` accepts it immediately — no retry/sleep."""

    def __init__(self, template: AgentMetrics | None):
        self._template = template
        self._ids = count(1)
        self.closed = False

    async def latest_for_user(self, user_id):
        if self._template is None:
            return None
        return replace(self._template, metrics_id=next(self._ids))

    async def close(self):
        self.closed = True


def _sample(n):
    qa = [LoCoMoQA(question=f"q-{i}", answer=f"a-{i}", category=1) for i in range(1, n + 1)]
    return LoCoMoSample(
        sample_id="m-1",
        qa=qa,
        conversation={
            "speaker_a": "A",
            "speaker_b": "B",
            "session_1_date_time": "1 Jan 2024",
            "session_1": [{"speaker": "A", "dia_id": "D1:1", "text": "hi"}],
        },
    )


def _env(monkeypatch):
    monkeypatch.setenv("PAM_API_HOST", "http://stub")
    monkeypatch.setenv("PAM_API_USER", "admin@stub")
    monkeypatch.setenv("PAM_API_PASSWORD", "pw")
    # A tokenizer model so prompt_tokens / output_tokens are actually counted.
    monkeypatch.setenv("PAM_OUTPUT_TOKEN_MODEL", "gpt-4o")


def test_agent_metrics_distributed_across_batch(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setattr(pam_baseline_mod, "PamClient", _StubPamClient)

    baseline = pam_baseline_mod.PamBaseline(batch_size=4)
    baseline._metrics_reader = _FakeReader(
        AgentMetrics(
            metrics_id=0,
            agent_input_tokens=400,
            agent_output_tokens=200,
            agent_model_used="agent-model-x",
            agent_cache_read_tokens=40,
            agent_cache_write_tokens=20,
            enriched_user_prompt_tokens=80,
        )
    )

    async def _go():
        await baseline.setup(seed=42)
        preds = await run_sample(_sample(4), baseline=baseline, seed=42, model_name="m")
        await baseline.teardown()
        return preds

    preds = asyncio.run(_go())

    # 400/4=100, 200/4=50, 40/4=10, 20/4=5, 80/4=20 — even across the 4 questions.
    assert [p.agent_input_tokens for p in preds] == [100, 100, 100, 100]
    assert [p.agent_output_tokens for p in preds] == [50, 50, 50, 50]
    assert [p.agent_cache_read_tokens for p in preds] == [10, 10, 10, 10]
    assert [p.agent_cache_write_tokens for p in preds] == [5, 5, 5, 5]
    assert [p.enriched_user_prompt_tokens for p in preds] == [20, 20, 20, 20]
    # The sample's totals reconstruct the batch metrics exactly.
    assert sum(p.agent_input_tokens for p in preds) == 400
    # prompt_tokens reflects the prompt WE sent to Pam: > 0 (and distributed
    # across the batch) even though input_tokens / context_tokens are 0.
    assert all(p.prompt_tokens > 0 for p in preds)
    assert all(p.input_tokens == 0 and p.context_tokens == 0 for p in preds)
    # model_used is surfaced for baseline_kwargs, not summed as a token count.
    assert baseline.baseline_kwargs_extra() == {"agent_model_used": "agent-model-x"}
    assert baseline._metrics_reader.closed is True


def test_no_metrics_row_yields_zero_agent_tokens(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setattr(pam_baseline_mod, "PamClient", _StubPamClient)

    baseline = pam_baseline_mod.PamBaseline(batch_size=3)
    baseline._metrics_reader = _FakeReader(None)  # DB unavailable / no rows

    async def _go():
        await baseline.setup(seed=42)
        return await run_sample(_sample(3), baseline=baseline, seed=42, model_name="m")

    preds = asyncio.run(_go())
    assert all(p.agent_input_tokens == 0 for p in preds)
    assert all(p.enriched_user_prompt_tokens == 0 for p in preds)
    # No model id captured → nothing added to baseline_kwargs.
    assert baseline.baseline_kwargs_extra() == {}


def test_remainder_spread_keeps_total_exact(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setattr(pam_baseline_mod, "PamClient", _StubPamClient)

    baseline = pam_baseline_mod.PamBaseline(batch_size=3)
    baseline._metrics_reader = _FakeReader(
        AgentMetrics(
            metrics_id=0,
            agent_input_tokens=10,  # 10 / 3 = [4, 3, 3]
            agent_output_tokens=0,
            agent_model_used=None,
            agent_cache_read_tokens=0,
            agent_cache_write_tokens=0,
            enriched_user_prompt_tokens=0,
        )
    )

    async def _go():
        await baseline.setup(seed=42)
        return await run_sample(_sample(3), baseline=baseline, seed=42, model_name="m")

    preds = asyncio.run(_go())
    assert [p.agent_input_tokens for p in preds] == [4, 3, 3]
    assert sum(p.agent_input_tokens for p in preds) == 10
