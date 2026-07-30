"""PamBaseline driven by the LoCoMo pipeline against a stub PamClient.

Asserts the per-sample lifecycle is wired correctly: login (once) → prepare
(create account + upload + memory build) → batched answer_batch → cleanup
(delete the just-finished conversation's account).
"""

from __future__ import annotations

import asyncio
import json
from itertools import count
from typing import Any

import pytest

from baselines.pam import baseline as pam_baseline_mod
from datasets.locomo.schemas import LoCoMoQA, LoCoMoSample
from tasks.locomo.pipeline import run_sample


class StubPamClient:
    """Records every call and returns canned Pam responses.

    `create_account` auto-increments `user_id` so multi-sample tests get
    distinct ids per conversation.
    """

    def __init__(self, host: str, api_key: str | None = None):
        self.host = host
        self.api_key = api_key
        self.user_id: int | None = None
        self.admin_token: str | None = None
        self.access_token: str | None = None
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._last_batch_size: int = 0
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

    def process_generic_files(
        self, files: list[tuple[str, bytes]], pam_exp_config: str | None = None
    ) -> list[str]:
        # Mirrors PamClient.process_generic_files: returns one run_id per batch
        # of up to MAX_FILES_PER_REQUEST files. For LoCoMo we always send 1
        # file → exactly 1 run_id.
        max_per = 5
        run_ids: list[str] = []
        for batch_start in range(0, len(files), max_per):
            batch = files[batch_start : batch_start + max_per]
            run_ids.append(f"run-{self.user_id}-{batch_start // max_per}")
            self._log(
                "process_generic_files",
                n_files=len(batch),
                names=[f[0] for f in batch],
                for_user_id=self.user_id,
                run_id=run_ids[-1],
            )
        return run_ids

    def wait_for_memory(self, run_ids: list[str], user_id: int | None = None) -> None:
        uid = user_id if user_id is not None else self.user_id
        self._log("wait_for_memory", run_ids=list(run_ids), user_id=uid)

    def send_message(self, prompt: str, conversation_id: str | None = None) -> tuple[str, int]:
        # Count questions in the rendered Q1.. block so each call returns the
        # right number of A1.. lines.
        n = sum(1 for line in prompt.splitlines() if line.startswith("Q"))
        self._last_batch_size = n
        self._log("send_message", n_questions=n, for_user_id=self.user_id)
        # Each answer encodes the question index so we can assert order downstream.
        lines = [f"A{i}: stub-answer-{i}" for i in range(1, n + 1)]
        return "\n".join(lines), 100 * n  # injected_tokens scales with batch

    def issue_user_tokens(self, user_id: int) -> str:
        # Mirrors PamClient.issue_user_tokens: sets a per-user access token so
        # chat runs as the reused user (not admin).
        self.user_id = user_id
        self.access_token = f"user-{user_id}-minted-token"
        self._log("issue_user_tokens", user_id=user_id)
        return self.access_token

    def delete_account(self, user_id: int | None = None) -> None:
        uid = user_id if user_id is not None else self.user_id
        self._log("delete_account", user_id=uid)


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
    # Expected: login -> create_account -> process_generic_files -> wait_for_memory
    #          -> 3x send_message -> delete_account
    assert methods == [
        "login",
        "create_account",
        "process_generic_files",
        "wait_for_memory",
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


def test_delete_runs_per_conversation(monkeypatch: pytest.MonkeyPatch) -> None:
    """One create+delete per conversation — each conversation's account is
    deleted as soon as its questions are answered, before the next conversation
    begins, so Pam never holds multiple memories for one user.
    """
    _set_env(monkeypatch)
    monkeypatch.setattr(pam_baseline_mod, "PamClient", StubPamClient)

    baseline = pam_baseline_mod.PamBaseline(batch_size=5)
    samples = [
        LoCoMoSample(
            sample_id=f"conv-{i}",
            qa=[LoCoMoQA(question=f"q-{i}", answer=f"a-{i}", category=1)],
            conversation={
                "speaker_a": "Alice",
                "speaker_b": "Bob",
                "session_1_date_time": "1 Jan 2024",
                "session_1": [{"speaker": "Alice", "dia_id": "D1:1", "text": "hi"}],
            },
        )
        for i in range(3)
    ]

    async def _go():
        await baseline.setup(seed=42)
        for s in samples:
            await run_sample(s, baseline=baseline, seed=42, model_name="gpt-4-turbo")
        await baseline.teardown()

    asyncio.run(_go())

    # Each conversation must produce exactly one create + one delete, and the
    # delete must follow that conversation's send_message (not be deferred).
    create_idx = [i for i, c in enumerate(baseline.client.calls) if c[0] == "create_account"]
    delete_idx = [i for i, c in enumerate(baseline.client.calls) if c[0] == "delete_account"]
    assert len(create_idx) == 3
    assert len(delete_idx) == 3
    # delete_i happens after create_i and before create_(i+1)
    for i in range(3):
        assert create_idx[i] < delete_idx[i]
        if i + 1 < 3:
            assert delete_idx[i] < create_idx[i + 1]

    # Each delete targets that conversation's freshly-created user id.
    deleted_ids = [c[1]["user_id"] for c in baseline.client.calls if c[0] == "delete_account"]
    assert deleted_ids == [12345, 12346, 12347]


def test_backup_memory_skips_delete_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--backup-memory` keeps the account entirely: no delete_account call,
    so the user + its built memory survive for later --pam-debug-user-id reuse."""
    _set_env(monkeypatch)
    monkeypatch.setattr(pam_baseline_mod, "PamClient", StubPamClient)

    baseline = pam_baseline_mod.PamBaseline(batch_size=1, backup_memory=True)
    sample = _sample(1)

    async def _go():
        await baseline.setup(seed=42)
        await run_sample(sample, baseline=baseline, seed=42, model_name="gpt-4-turbo")
        await baseline.teardown()

    asyncio.run(_go())

    methods = [c[0] for c in baseline.client.calls]
    # Account is created and questioned, but never deleted.
    assert "create_account" in methods
    assert "send_message" in methods
    assert "delete_account" not in methods


def test_no_backup_memory_deletes_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without --backup-memory the per-conversation account is wiped."""
    _set_env(monkeypatch)
    monkeypatch.setattr(pam_baseline_mod, "PamClient", StubPamClient)

    baseline = pam_baseline_mod.PamBaseline(batch_size=1)
    sample = _sample(1)

    async def _go():
        await baseline.setup(seed=42)
        await run_sample(sample, baseline=baseline, seed=42, model_name="gpt-4-turbo")
        await baseline.teardown()

    asyncio.run(_go())

    delete_calls = [c for c in baseline.client.calls if c[0] == "delete_account"]
    assert len(delete_calls) == 1
    assert delete_calls[0][1]["user_id"] == 12345


def test_debug_user_id_skips_create_upload_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    """--pam-debug-user-id reuses an existing user: skip create/upload/memory
    build and delete, but mint a per-user token so chat runs as THAT user
    (queries its existing memory, not the admin's)."""
    _set_env(monkeypatch)
    monkeypatch.setattr(pam_baseline_mod, "PamClient", StubPamClient)

    baseline = pam_baseline_mod.PamBaseline(batch_size=5, debug_user_id=999, api_key="harmix-key")
    sample = _sample(5)

    async def _go():
        await baseline.setup(seed=42)
        await run_sample(sample, baseline=baseline, seed=42, model_name="gpt-4-turbo")
        await baseline.teardown()

    asyncio.run(_go())

    methods = [call[0] for call in baseline.client.calls]
    # login -> mint per-user token -> chat. No create / upload / memory build,
    # and no delete_account.
    assert methods == ["login", "issue_user_tokens", "send_message"]
    mint_call = next(c for c in baseline.client.calls if c[0] == "issue_user_tokens")
    assert mint_call[1]["user_id"] == 999
    assert baseline.client.user_id == 999
    # Chat runs with the minted per-user token, NOT the admin token.
    assert baseline.client.access_token == "user-999-minted-token"


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

    upload_call = next(c for c in baseline.client.calls if c[0] == "process_generic_files")
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
    # memory_creation_duration_sec is wall-clock; the stub returns immediately
    # so we just assert it's a non-negative float.
    assert isinstance(extras["memory_creation_duration_sec"], float)
    assert extras["memory_creation_duration_sec"] >= 0.0
    # run_id(s) returned by process_generic_files are tracked on the baseline
    # and surfaced via extras for traceability in Mongo.
    assert extras["pam_memory_run_ids"] == ["run-12345-0"]


def test_wait_for_memory_called_with_returned_run_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`wait_for_memory` must receive the exact run_id list that
    `process_generic_files` returned — that's the contract between the two
    Pam endpoints."""
    _set_env(monkeypatch)
    monkeypatch.setattr(pam_baseline_mod, "PamClient", StubPamClient)

    baseline = pam_baseline_mod.PamBaseline(batch_size=1)
    sample = _sample(1)

    async def _go():
        await baseline.setup(seed=42)
        await run_sample(sample, baseline=baseline, seed=42, model_name="gpt-4-turbo")

    asyncio.run(_go())

    process_call = next(c for c in baseline.client.calls if c[0] == "process_generic_files")
    wait_call = next(c for c in baseline.client.calls if c[0] == "wait_for_memory")
    assert wait_call[1]["run_ids"] == [process_call[1]["run_id"]]
    assert wait_call[1]["user_id"] == process_call[1]["for_user_id"]


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
        def process_generic_files(self, files, pam_exp_config=None):  # type: ignore[override]
            self.last_payloads = [(name, body) for name, body in files]
            return super().process_generic_files(files)

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
