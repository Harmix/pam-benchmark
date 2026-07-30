"""Pam batch retry: resend a batch that comes back with zero answers."""

from __future__ import annotations

import asyncio

from baselines.pam import baseline as pam_baseline_mod
from datasets.locomo.schemas import LoCoMoQA, LoCoMoSample
from tasks.locomo.pipeline import run_sample


class _ScriptedClient:
    """send_message returns canned replies from a per-call script.

    Each script entry is the raw answer text for that call; `_answers(k)` builds
    a full `A1..Ak` block, and `""` simulates a 0/N (no-answer) reply.
    """

    def __init__(self, host, api_key=None):
        self.user_id = None
        self.access_token = None
        self.send_calls = 0
        self._script: list[str] = []

    def login(self, email, password):
        return "admin-token"

    def create_account(self, **kwargs):
        self.user_id = 401
        self.access_token = "user-401-token"
        return {"user": {"id": 401}, "tokens": {"access_token": self.access_token}}

    def process_generic_files(self, files, pam_exp_config=None):
        return ["run-401-0"]

    def wait_for_memory(self, run_ids, user_id=None):
        return None

    def send_message(self, prompt, conversation_id=None):
        idx = self.send_calls
        self.send_calls += 1
        text = self._script[idx] if idx < len(self._script) else self._script[-1]
        return text, 0

    def delete_account(self, user_id=None):
        return None


def _full(k: int) -> str:
    return "\n".join(f"A{i}: ans-{i}" for i in range(1, k + 1))


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


def _run(monkeypatch, script: list[str], batch_size: int):
    _env(monkeypatch)
    monkeypatch.setattr(pam_baseline_mod, "PamClient", _ScriptedClient)
    baseline = pam_baseline_mod.PamBaseline(batch_size=batch_size)
    baseline.client._script = script

    async def _go():
        await baseline.setup(seed=1)
        preds = await run_sample(_sample(batch_size), baseline=baseline, seed=1, model_name="m")
        await baseline.teardown()
        return preds, baseline

    return asyncio.run(_go())


def test_zero_answers_retries_twice_then_gives_up(monkeypatch):
    # Every attempt returns no answers → 1 original + 2 retries = 3 send calls.
    preds, baseline = _run(monkeypatch, script=[""], batch_size=4)
    assert baseline.client.send_calls == 3
    assert all(p.model_answer == "" for p in preds)


def test_zero_answers_recovers_on_first_retry(monkeypatch):
    # First call empty, second call full → 2 send calls, answers populated.
    preds, baseline = _run(monkeypatch, script=["", _full(4)], batch_size=4)
    assert baseline.client.send_calls == 2
    assert [p.model_answer for p in preds] == ["ans-1", "ans-2", "ans-3", "ans-4"]


def test_partial_answers_do_not_retry(monkeypatch):
    # 2 of 4 answered (slots 1,3) — a partial reply is accepted, no retry.
    partial = "A1: ans-1\nA3: ans-3"
    preds, baseline = _run(monkeypatch, script=[partial], batch_size=4)
    assert baseline.client.send_calls == 1
    assert preds[0].model_answer == "ans-1"
    assert preds[1].model_answer == ""
    assert preds[2].model_answer == "ans-3"


def test_full_answers_do_not_retry(monkeypatch):
    preds, baseline = _run(monkeypatch, script=[_full(4)], batch_size=4)
    assert baseline.client.send_calls == 1
    assert all(p.model_answer for p in preds)
