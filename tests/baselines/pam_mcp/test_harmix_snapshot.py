"""PamMcpBaseline on the Harmix path: memory is built from a pre-staged GCS
snapshot via `process_snapshot` (with mapped `--sources`) instead of an uploaded
conversation via `process_generic_files`."""

from __future__ import annotations

import asyncio
from itertools import count
from typing import Any

from baselines.pam_mcp import baseline as pam_mcp_mod
from baselines.pam_mcp.baseline import PamMcpBaseline
from datasets.harmix.schemas import HarmixCase, HarmixEnvironment, HarmixSample
from tasks.harmix.pipeline import run_sample


class StubPamClient:
    """Records calls; exposes both the upload and snapshot memory-build paths."""

    def __init__(self, host: str, api_key: str | None = None):
        self.host = host
        self.base_url = f"{host.rstrip('/')}/v1"
        self.api_key = api_key
        self.user_id: int | None = None
        self.admin_token: str | None = None
        self.access_token: str | None = None
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._next_user_id = count(555)

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

    def process_snapshot(self, snapshot_uri: str, sources: list[str]) -> str:
        run_id = f"snap-run-{self.user_id}"
        self._log(
            "process_snapshot",
            snapshot_uri=snapshot_uri,
            sources=list(sources),
            for_user_id=self.user_id,
            run_id=run_id,
        )
        return run_id

    def process_generic_files(self, files: list[tuple[str, bytes]]) -> list[str]:
        self._log("process_generic_files", n_files=len(files))
        return [f"run-{self.user_id}-0"]

    def wait_for_memory(self, run_ids: list[str], user_id: int | None = None) -> None:
        self._log("wait_for_memory", run_ids=list(run_ids), user_id=self.user_id)

    def rotate_developer_key(self) -> str:
        key = f"pam_mkey_uid{self.user_id}.secret-xyz"
        self._log("rotate_developer_key", for_user_id=self.user_id, key=key)
        return key

    def delete_account(self, user_id: int | None = None) -> None:
        self._log("delete_account", user_id=user_id if user_id is not None else self.user_id)


def _harmix_sample(n: int) -> HarmixSample:
    env = HarmixEnvironment(
        id="nazar",
        name="Nazar",
        memory_sources=["emails", "meetings"],
        memory_snapshot="gs://pam-dev-memory-data/benchmark/datasets/harmix/nazar.zip",
    )
    cases = [
        HarmixCase(
            id=f"nazar-{i}", environment="nazar", question=f"q-{i}", expected_answer=f"a-{i}"
        )
        for i in range(1, n + 1)
    ]
    return HarmixSample(environment=env, cases=cases)


def _baseline(monkeypatch, tmp_path, fake_harness_factory, **kw) -> PamMcpBaseline:
    monkeypatch.setenv("PAM_API_HOST", "https://staging.api.pam.harmix.ai")
    monkeypatch.setenv("PAM_API_USER", "admin@stub")
    monkeypatch.setenv("PAM_API_PASSWORD", "stub-password")
    monkeypatch.setattr(pam_mcp_mod, "PamClient", StubPamClient)
    return PamMcpBaseline(
        harness=fake_harness_factory(model="gpt-4o"),
        harness_model="gpt-4o",
        output_root=tmp_path / "out",
        **kw,
    )


def test_snapshot_path_calls_process_snapshot_with_mapped_sources(
    monkeypatch, tmp_path, fake_harness_factory
):
    baseline = _baseline(monkeypatch, tmp_path, fake_harness_factory, batch_size=1)
    sample = _harmix_sample(2)

    async def _go():
        await baseline.setup(seed=42)
        preds = await run_sample(sample, baseline=baseline, seed=42, model_name="pam_mcp")
        await baseline.teardown()
        return preds

    preds = asyncio.run(_go())

    methods = [c[0] for c in baseline.client.calls]
    # Snapshot path: process_snapshot, NOT process_generic_files.
    assert "process_snapshot" in methods
    assert "process_generic_files" not in methods
    assert methods == [
        "login",
        "create_account",
        "process_snapshot",
        "wait_for_memory",
        "rotate_developer_key",
        "delete_account",
    ]

    snap = next(c for c in baseline.client.calls if c[0] == "process_snapshot")[1]
    assert snap["snapshot_uri"] == sample.memory_snapshot
    # memory_sources ["emails","meetings"] → pipeline keys.
    assert snap["sources"] == ["gmail", "meeting_transcripts"]

    # batch_size default 1 → one harness answer call per case; the fake numbers
    # answers within each single-question batch, so each is "ans-1".
    assert baseline.harness.answer_calls == 2
    assert [p.model_answer for p in preds] == ["ans-1", "ans-1"]
    assert [p.case_id for p in preds] == ["nazar-1", "nazar-2"]
    assert baseline.extras()["pam_memory_run_ids"] == ["snap-run-555"]


def test_raw_prompt_sends_question_verbatim_and_keeps_full_answer(
    monkeypatch, tmp_path, fake_harness_factory
):
    # A realistic long answer that the numbered-batch protocol would have
    # squeezed into a terse "A1:" line — raw mode must keep it whole.
    answer = (
        "You have two people named Yaroslav: Yaroslav Morozevych (co-founder, "
        "joined at founding) and Yaroslav Kravchenko (full-time ~Nov 11, 2025)."
    )
    harness = fake_harness_factory(model="gpt-4o", script=[answer])
    baseline = _baseline(
        monkeypatch,
        tmp_path,
        lambda **_: harness,
        raw_prompt=True,
        batch_size=10,  # must be overridden to 1 by raw mode
    )
    sample = _harmix_sample(2)

    async def _go():
        await baseline.setup(seed=42)
        preds = await run_sample(sample, baseline=baseline, seed=42, model_name="pam_mcp")
        await baseline.teardown()
        return preds

    preds = asyncio.run(_go())

    # raw_prompt forces batch size 1 regardless of the requested batch_size.
    assert baseline.batch_size == 1
    assert baseline.extras()["raw_prompt"] is True

    # Each question is sent to the harness VERBATIM: no numbered-batch
    # scaffolding, no "A1: <short answer>" template, no extra instructions.
    assert harness.sent_prompts == ["q-1", "q-2"]

    # The full model reply is kept as the answer (not collapsed to an A1: line).
    assert [p.model_answer for p in preds] == [answer, answer]
