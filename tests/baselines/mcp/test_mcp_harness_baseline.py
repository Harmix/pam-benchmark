"""McpHarnessBaseline driven through the LoCoMo pipeline against a fake harness.

Asserts: build-then-batch lifecycle, token mapping (real usage → columns,
injected/enriched = None), 0-answer retry, and memory cleanup vs keep.
"""

from __future__ import annotations

import asyncio

from baselines.mcp.base import McpHarnessBaseline
from baselines.mcp.memory_md.backend import MemoryMdBackend
from datasets.locomo.schemas import LoCoMoQA, LoCoMoSample
from tasks.locomo.pipeline import run_sample


def _sample(n):
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


def _baseline(fake_harness_factory, tmp_path, *, batch_size=4, keep_memory=False, script=None):
    harness = fake_harness_factory(model="gpt-4o", script=script)
    return McpHarnessBaseline(
        harness=harness,
        backend=MemoryMdBackend(),
        output_root=tmp_path / "out",
        batch_size=batch_size,
        harness_model="gpt-4o",
        keep_memory=keep_memory,
    )


def test_build_then_batch_lifecycle_and_token_mapping(fake_harness_factory, tmp_path):
    baseline = _baseline(fake_harness_factory, tmp_path, batch_size=4)

    async def _go():
        await baseline.setup(seed=1)
        preds = await run_sample(_sample(4), baseline=baseline, seed=1, model_name="m")
        await baseline.teardown()
        return preds

    preds = asyncio.run(_go())

    # 1 ingest (memory build) + 1 answer call.
    phases = [c["phase"] for c in baseline.harness.calls]
    assert phases == ["ingest", "answer"]
    # answer phase is read-only (no Write/Edit).
    answer_tools = next(
        c["allowed_tools"] for c in baseline.harness.calls if c["phase"] == "answer"
    )
    assert "Write" not in answer_tools and "Edit" not in answer_tools

    assert [p.model_answer for p in preds] == ["ans-1", "ans-2", "ans-3", "ans-4"]
    # 400/4=100 input, 200/4=50 output, 40/4=10 cache-read, 20/4=5 cache-write per q.
    assert [p.input_tokens for p in preds] == [100, 100, 100, 100]
    assert [p.output_tokens for p in preds] == [50, 50, 50, 50]
    assert [p.agent_cache_read_tokens for p in preds] == [10, 10, 10, 10]
    assert [p.agent_cache_write_tokens for p in preds] == [5, 5, 5, 5]
    # cost 0.8 / 4 = 0.2 per question; latency 1000 / 4 = 250.
    assert all(abs(p.est_cost_usd - 0.2) < 1e-9 for p in preds)
    assert all(abs(p.latency_ms - 250.0) < 1e-9 for p in preds)
    # prompt_tokens > 0 (counted with gpt-4o); context = input - prompt >= 0.
    assert all(p.prompt_tokens > 0 for p in preds)
    assert all(p.context_tokens == p.input_tokens - p.prompt_tokens for p in preds)
    # injected/enriched are None for claude-code-style baselines.
    assert all(p.injected_tokens is None for p in preds)
    assert all(p.enriched_user_prompt_tokens is None for p in preds)

    extras = baseline.extras()
    assert extras["harness"] == "fake"
    assert extras["harness_model"] == "gpt-4o"
    assert extras["memory_backend"] == "memory_md_mcp"
    assert baseline.baseline_kwargs_extra() == {
        "harness": "fake",
        "harness_model": "gpt-4o",
        "memory_backend": "memory_md_mcp",
    }


def test_zero_answers_retries_twice_then_gives_up(fake_harness_factory, tmp_path):
    baseline = _baseline(fake_harness_factory, tmp_path, batch_size=3, script=[""])

    async def _go():
        await baseline.setup(seed=1)
        return await run_sample(_sample(3), baseline=baseline, seed=1, model_name="m")

    preds = asyncio.run(_go())
    # 1 original + 2 retries = 3 answer calls.
    assert baseline.harness.answer_calls == 3
    assert all(p.model_answer == "" for p in preds)


def test_zero_answers_recovers_on_retry(fake_harness_factory, tmp_path):
    full = "\n".join(f"A{i}: got-{i}" for i in range(1, 4))
    baseline = _baseline(fake_harness_factory, tmp_path, batch_size=3, script=["", full])

    async def _go():
        await baseline.setup(seed=1)
        return await run_sample(_sample(3), baseline=baseline, seed=1, model_name="m")

    preds = asyncio.run(_go())
    assert baseline.harness.answer_calls == 2
    assert [p.model_answer for p in preds] == ["got-1", "got-2", "got-3"]


def test_cleanup_wipes_memory_by_default(fake_harness_factory, tmp_path):
    baseline = _baseline(fake_harness_factory, tmp_path, batch_size=2, keep_memory=False)

    async def _go():
        await baseline.setup(seed=1)
        await run_sample(_sample(2), baseline=baseline, seed=1, model_name="m")

    asyncio.run(_go())
    assert not (tmp_path / "out" / "conv-x").exists()


def test_keep_memory_retains_dir(fake_harness_factory, tmp_path):
    baseline = _baseline(fake_harness_factory, tmp_path, batch_size=2, keep_memory=True)

    async def _go():
        await baseline.setup(seed=1)
        await run_sample(_sample(2), baseline=baseline, seed=1, model_name="m")

    asyncio.run(_go())
    assert (tmp_path / "out" / "conv-x" / "memory").exists()
