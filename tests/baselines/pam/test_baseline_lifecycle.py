"""PamBaseline driven by the LoCoMo pipeline against a stub PamClient.

Asserts the per-sample lifecycle is wired correctly: login → prepare (create
account + upload + memory build) → batched answer_batch → cleanup (delete).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from baselines.pam import baseline as pam_baseline_mod
from datasets.locomo.schemas import LoCoMoQA, LoCoMoSample
from tasks.locomo.pipeline import run_sample


class StubPamClient:
    """Records every call and returns canned Pam responses."""

    def __init__(self, host: str):
        self.host = host
        self.user_id: int | None = None
        self.admin_token: str | None = None
        self.access_token: str | None = None
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._last_batch_size: int = 0

    def _log(self, method: str, **kwargs: Any) -> None:
        self.calls.append((method, kwargs))

    def login(self, email: str, password: str) -> str:
        self._log("login", email=email)
        self.admin_token = "admin-token"
        return self.admin_token

    def create_account(self, **kwargs: Any) -> dict[str, Any]:
        self._log("create_account", **kwargs)
        self.user_id = 12345
        self.access_token = "user-token"
        return {"user": {"id": self.user_id}, "tokens": {"access_token": self.access_token}}

    def upload_generic_files(self, files: list[tuple[str, bytes]]) -> list[dict[str, Any]]:
        self._log("upload_generic_files", n_files=len(files), names=[f[0] for f in files])
        return [{"filename": f[0]} for f in files]

    def create_memory(self, **kwargs: Any) -> dict[str, Any]:
        self._log("create_memory")
        return {"message": "ok"}

    def send_message(self, prompt: str, conversation_id: str | None = None) -> tuple[str, int]:
        # Count questions in the rendered Q1.. block so each call returns the
        # right number of A1.. lines.
        n = sum(1 for line in prompt.splitlines() if line.startswith("Q"))
        self._last_batch_size = n
        self._log("send_message", n_questions=n)
        # Each answer encodes the question index so we can assert order downstream.
        lines = [f"A{i}: stub-answer-{i}" for i in range(1, n + 1)]
        return "\n".join(lines), 100 * n  # injected_tokens scales with batch

    def delete_account(self) -> None:
        self._log("delete_account", user_id=self.user_id)


def _sample(n_questions: int) -> LoCoMoSample:
    qa = [
        LoCoMoQA(question=f"q-{i}", answer=f"a-{i}", category=1) for i in range(1, n_questions + 1)
    ]
    return LoCoMoSample(
        sample_id="lifecycle-1",
        qa=qa,
        conversation={
            "speaker_a": "Alice",
            "speaker_b": "Bob",
            "session_1_date_time": "1 Jan 2024",
            "session_1": [{"speaker": "Alice", "dia_id": "D1:1", "text": "hi"}],
        },
    )


def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAM_API_HOST", "http://stub")
    monkeypatch.setenv("PAM_API_USER", "admin@stub")
    monkeypatch.setenv("PAM_API_PASSWORD", "stub-password")


def test_lifecycle_call_order_with_batching(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    monkeypatch.setattr(pam_baseline_mod, "PamClient", StubPamClient)

    baseline = pam_baseline_mod.PamBaseline(batch_size=10)
    sample = _sample(25)

    async def _go():
        await baseline.setup(seed=42)
        preds = await run_sample(sample, baseline=baseline, seed=42, model_name="gpt-4-turbo")
        await baseline.teardown()
        return preds

    preds = asyncio.run(_go())

    methods = [call[0] for call in baseline.client.calls]
    # Expected: login -> create_account -> upload -> create_memory -> 3x send_message -> delete_account
    assert methods == [
        "login",
        "create_account",
        "upload_generic_files",
        "create_memory",
        "send_message",
        "send_message",
        "send_message",
        "delete_account",
    ]
    send_calls = [call for call in baseline.client.calls if call[0] == "send_message"]
    assert [c[1]["n_questions"] for c in send_calls] == [10, 10, 5]

    # 25 predictions, ordered, with stubbed answers
    assert len(preds) == 25
    assert preds[0].model_answer == "stub-answer-1"
    assert preds[9].model_answer == "stub-answer-10"
    # Second batch resets index → first answer of batch 2 is "stub-answer-1" again
    assert preds[10].model_answer == "stub-answer-1"


def test_debug_user_id_skips_create_upload_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    monkeypatch.setattr(pam_baseline_mod, "PamClient", StubPamClient)

    baseline = pam_baseline_mod.PamBaseline(batch_size=5, debug_user_id=999)
    sample = _sample(5)

    async def _go():
        await baseline.setup(seed=42)
        await run_sample(sample, baseline=baseline, seed=42, model_name="gpt-4-turbo")
        await baseline.teardown()

    asyncio.run(_go())

    methods = [call[0] for call in baseline.client.calls]
    # No create_account / upload / create_memory; no delete_account either.
    assert methods == ["login", "send_message"]
    assert baseline.client.user_id == 999


def test_serialize_upload_payload_matches_sample(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    monkeypatch.setattr(pam_baseline_mod, "PamClient", StubPamClient)

    baseline = pam_baseline_mod.PamBaseline(batch_size=5)
    sample = _sample(5)

    async def _go():
        await baseline.setup(seed=42)
        await run_sample(sample, baseline=baseline, seed=42, model_name="gpt-4-turbo")
        await baseline.teardown()

    asyncio.run(_go())

    upload_call = next(c for c in baseline.client.calls if c[0] == "upload_generic_files")
    assert upload_call[1]["n_files"] == 1
    assert upload_call[1]["names"] == [f"{sample.sample_id}_conversation.json"]


def test_extras_carries_memory_duration_and_user_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    monkeypatch.setattr(pam_baseline_mod, "PamClient", StubPamClient)

    baseline = pam_baseline_mod.PamBaseline(batch_size=3)
    sample = _sample(3)

    async def _go():
        await baseline.setup(seed=42)
        await run_sample(sample, baseline=baseline, seed=42, model_name="gpt-4-turbo")

    asyncio.run(_go())

    extras = baseline.extras()
    assert extras["pam_user_id"] == 12345
    assert extras["pam_batch_size"] == 3
    # memory_creation_duration_sec is wall-clock; stubbed create_memory returns
    # quickly so we just assert it's a float >= 0.
    assert isinstance(extras["memory_creation_duration_sec"], float)
    assert extras["memory_creation_duration_sec"] >= 0.0


def test_per_question_injected_tokens_distributed(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    monkeypatch.setattr(pam_baseline_mod, "PamClient", StubPamClient)

    baseline = pam_baseline_mod.PamBaseline(batch_size=4)
    sample = _sample(4)

    async def _go():
        await baseline.setup(seed=42)
        return await run_sample(sample, baseline=baseline, seed=42, model_name="gpt-4-turbo")

    preds = asyncio.run(_go())
    # Stub returns injected_tokens = 100 * batch_size (4 here → 400 total).
    # PamBaseline distributes evenly: 400 / 4 = 100 per question.
    assert all(p.injected_tokens == 100 for p in preds)


def test_unused_payload_shape_holds_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Smoke: the serialized payload uploaded to the stub is valid JSON with
    the sample_id baked in (covers the integration between serializer + baseline).
    """
    _set_env(monkeypatch)

    class CapturingStub(StubPamClient):
        def upload_generic_files(self, files):  # type: ignore[override]
            self.last_payloads = [(name, body) for name, body in files]
            return super().upload_generic_files(files)

    monkeypatch.setattr(pam_baseline_mod, "PamClient", CapturingStub)
    baseline = pam_baseline_mod.PamBaseline(batch_size=1)
    sample = _sample(1)

    async def _go():
        await baseline.setup(seed=42)
        await run_sample(sample, baseline=baseline, seed=42, model_name="gpt-4-turbo")

    asyncio.run(_go())
    name, body = baseline.client.last_payloads[0]
    assert name.endswith("_conversation.json")
    payload = json.loads(body)
    assert payload["sample_id"] == sample.sample_id
