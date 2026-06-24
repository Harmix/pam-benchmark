# M2 — Pam baseline for LoCoMo (planning)

**Status:** Shipped. The Pam baseline described here lives in `src/baselines/pam/` and runs via `--baseline pam`; see [`src/baselines/pam/README.md`](../src/baselines/pam/README.md) for the as-built behavior. This document is the original design plan, kept for context.

**Owner:** Denys

**Reference implementation:** `pam-benchmark-main/tasks/memtrack/environment/run_memtrack_pam_v2.py` (MemTrack-shaped; we adapt the API interaction, drop everything MemTrack-specific, and fit it into our async harness).

---

## 1. Goal & non-goals

**Goal.** Add a `pam` baseline that evaluates Pam end-to-end on LoCoMo, reusing exactly the same scorer (F1 + LLM-as-judge), Mongo schema, reports, and CLI surface as the M1 `gpt-4-turbo` baseline — so a side-by-side Pam-vs-GPT table falls out for free.

**Non-goals.**
- No competitor baselines (Honcho, Supermemory, mem0, Zep) — those are M4.
- No new datasets — LoCoMo only.
- No multi-turn chat over the same `conversation_id`; one SSE call per **batch**, matching the spirit of the reference but with batching enabled (see §3.5).
- No `backup_workspace` call from this benchmark — Pam already handles workspace backup server-side.
- No web UI / live dashboard — reports come from `scripts/generate_report.py` as today.
- No question-range scoping flags (`QUESTION_RANGE_*`) — out of scope for M2.

---

## 2. The Pam-shaped lifecycle (and why it doesn't fit `Baseline` as-is)

Current `Baseline` protocol (`src/baselines/base.py:27`):

```
await baseline.setup(seed=...)        # once per process
for prompt in prompts:
    r = await baseline.answer(prompt) # once per question
await baseline.teardown()              # once per process
```

That works because `LiteLLMBaseline` is stateless across samples and questions — every prompt is self-contained (the full conversation is packed in by `build_prompt`).

Pam is the opposite. LoCoMo has 10 samples; each sample is one multi-session conversation between two people. **One conversation → one Pam memory → all of that sample's questions answered against that single memory.** Within a sample, multiple questions can be answered in one batched SSE call. The lifecycle that actually matches Pam is:

```
await baseline.setup(seed=...)                       # admin login
for sample in samples:
    await baseline.prepare_for_sample(sample)        # account + upload conversation.json + memory pipeline
    for chunk in chunks(sample.qa, batch_size):
        responses = await baseline.answer_batch(prompts)   # one SSE call per chunk
    await baseline.cleanup_sample()                  # delete account
await baseline.teardown()
```

This mirrors MemTrack's `process_config_pam` (1 memory per config, N questions) but ports it cleanly to LoCoMo's "1 memory per conversation" shape and reduces wall time via batching.

---

## 3. Architecture changes

### 3.1 Extend the `Baseline` protocol with three optional hooks

In `src/baselines/base.py`, add **optional** lifecycle hooks so the LoCoMo pipeline can call them unconditionally without breaking `LiteLLMBaseline`. A tiny `BaselineBase` adapter provides default no-ops / per-prompt fallbacks:

```python
# new optional methods on the Protocol — default behavior preserves LiteLLM exactly
async def prepare_for_sample(self, sample: Any) -> None: ...   # default: no-op
async def cleanup_sample(self) -> None: ...                    # default: no-op
async def answer_batch(self, prompts: list[str]) -> list[BaselineResponse]: ...
    # default: [await self.answer(p) for p in prompts]
```

`LiteLLMBaseline` inherits the no-op + per-prompt-loop defaults and continues to work unchanged.

### 3.2 Extend `TokenUsage` with `injected_tokens`

Pam's SSE stream reports `injected_tokens` (how many tokens from memory the retriever fed to the answering model). It's the closest analog to "input tokens" for a memory product and we want it in the report. Smallest change: add `injected_tokens: int = 0` to `TokenUsage` in `src/baselines/base.py`. LiteLLM leaves it at 0; Pam fills it in.

### 3.3 Per-sample timing on the Mongo document

`memory_creation_duration_sec` is a per-sample metric (not per-question). Add an optional `extras: dict[str, Any]` slot on the per-sample handoff so a baseline can ship additional sample-level metrics (e.g. `{"memory_creation_duration_sec": 184.2, "pam_user_id": 12345}`). The runner merges it into the Mongo document alongside `_aggregate`. LiteLLM produces an empty dict.

### 3.4 LoCoMo pipeline — branch on "does the baseline use external memory?"

Currently `tasks/locomo/pipeline.py:41` always calls `build_prompt(sample, qa, model=...)` which packs the entire conversation into every prompt. Pam doesn't want that — the conversation is already in its memory; the prompt should be just the question (or batch of questions).

Cleanest split: **the baseline declares whether it has external memory.** Add a class attribute `external_memory: bool` on `Baseline` (default `False` = harness packs context, like LiteLLM today). Pam sets it to `True`. The LoCoMo pipeline does:

```python
if baseline.external_memory:
    built = build_bare_prompt(qa, seed=seed)               # just the question (and cat-5 MC)
else:
    built = build_prompt(sample, qa, model=model_name, seed=seed)  # pack conversation
```

`build_bare_prompt` is a new small helper in `tasks/locomo/prompts.py` that reuses the existing cat-2 (temporal) and cat-5 (adversarial MC) question-shaping logic but skips `build_conversation_context`. The cat-5 random `(a)/(b)` ordering stays seeded so a Pam run and a GPT run see identical MC layouts at the same seed.

### 3.5 Batched questions (Pam-only)

For external-memory baselines we can answer multiple questions per SSE call. The pipeline chunks the per-sample question list by `baseline.batch_size` (class attribute, default `1` for LiteLLM, `10` for Pam) and calls `answer_batch`:

```python
batch_size = getattr(baseline, "batch_size", 1)
for chunk in chunked(qa_items, batch_size):
    prompts = [built_for(qa).prompt for qa in chunk]
    responses = await baseline.answer_batch(prompts)
    for qa, response in zip(chunk, responses, strict=True):
        # build LoCoMoPrediction as today
```

For LiteLLM (`batch_size = 1`), this degenerates to the existing per-question loop — no behavioral change, no perf regression.

**Pam batching protocol.** `PamBaseline.answer_batch` renders one numbered prompt:

```
Answer each of the following questions about the conversation. Reply in the
EXACT format:
A1: <short answer>
A2: <short answer>
...

Q1: <question 1>
Q2: <question 2>
...
```

A single SSE call returns the full text; a small parser extracts `A1`/`A2`/... lines via regex. If the response is short by some `Ai` (parser miss), missing slots get an empty answer and an `error_note` in the prediction so the F1 scorer/judge still get something to score (matching how a single failed call would behave today).

**Per-question metric distribution from one batched SSE call:**
- `latency_ms` = total_batch_latency / N
- `injected_tokens` = total_batch_injected / N (rounded)
- `output_tokens` = tiktoken-counted on each parsed answer individually
- `input_tokens` = 0 (Pam doesn't expose its underlying LLM's input count)
- `est_cost_usd` = 0.0 (Pam is internal infra)

Batch size is exposed as `--pam-batch-size` (default 10) so we can tune it without a code change.

### 3.6 CLI additions

`src/cli.py` gains two flags, both Pam-specific:

| Flag | Default | Forwarded to |
|---|---|---|
| `--pam-batch-size` | `10` | `RunConfig.pam_batch_size`, picked up by `PamBaseline` |
| `--pam-debug-user-id` | `None` (disabled) | `RunConfig.pam_debug_user_id`; when set, `prepare_for_sample` reuses this Pam user and skips create / upload / memory-build |

Both come from the CLI only — no env-var fallback. Existing flags are unchanged.

---

## 4. New files

```
src/baselines/pam/
├── __init__.py
├── README.md         # 1-pager: how the Pam baseline plugs in (mirrors LiteLLM's README)
├── baseline.py       # PamBaseline: implements Baseline; owns lifecycle + batching
├── client.py         # PamClient: ported from the reference, with Pam naming
└── serialize.py      # LoCoMoSample → [("conversation.json", json_bytes)]
```

### 4.1 `client.py` — what changes vs. the reference

A near-line-for-line port of the `PAMClient` class from the reference, with these adjustments:

- **Naming:** class stays `PamClient` (not `PAMClient`); all comments and log strings use "Pam".
- **Retry library:** replace `backoff` with `tenacity` (already a dep) for consistency with `utils/llm.py`. Same retry budgets — 3 attempts for transient HTTP errors, exponential backoff.
- **Auth + token refresh:** kept verbatim — `login`, `_login_as`, `refresh_token` (admin + user), 401 retry-after-refresh on `delete_account` / `trigger_memory_pipeline` / `poll_memory_status` / `send_message`.
- **Memory pipeline polling:** kept verbatim — `MEMORY_POLL_INTERVAL = 30s`, `MAX_CONSECUTIVE_POLL_ERRORS = 3`, terminal-status detection, error propagation when pipeline `failed`/`stopped`/`cancelled`. The user explicitly called this out as required, so it ships unchanged.
- **SSE answer extraction:** kept verbatim — multi-turn buffer, tool-use boundary detection, `injected_tokens` extraction from the terminal `role: result` payload.
- **File upload batching:** kept verbatim — `MAX_FILES_PER_REQUEST = 5` (irrelevant for LoCoMo since we upload exactly 1 file per sample, but harmless to keep).
- **Removed:** `backup_workspace` is dropped entirely (Pam handles workspace backup server-side).

The client stays **sync** (uses `requests`) — the reference is sync and this keeps the port faithful. We wrap it in `asyncio.to_thread(...)` at the `PamBaseline.answer_batch` / `prepare_for_sample` boundary so the event loop isn't blocked by 30-second polls or 600-second SSE timeouts. New dep: `requests` (single, well-known package — no controversy).

### 4.2 `serialize.py` — LoCoMo conversation → upload payload

One JSON file per sample preserving the original structure from `src/datasets/locomo/data/locomo10.json` exactly:

```python
def serialize_sample(sample: LoCoMoSample) -> list[tuple[str, bytes]]:
    payload = {
        "sample_id": sample.sample_id,
        "speaker_a": sample.conversation.get("speaker_a"),
        "speaker_b": sample.conversation.get("speaker_b"),
        # Session_1, session_1_date_time, session_2, session_2_date_time, ...
        # in original order from the source JSON (insertion-order preserved).
        **{k: v for k, v in sample.conversation.items() if k.startswith("session_")},
    }
    fname = f"{sample.sample_id}_conversation.json"
    return [(fname, json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))]
```

This satisfies your spec: one JSON per conversation, all session metadata + `*_date_time` timestamps, sessions in the original order. Pam ingests this single file and builds the memory.

### 4.3 `baseline.py` — `PamBaseline`

```python
class PamBaseline(Baseline):
    name = "pam"
    track = "memory_product"
    external_memory = True
    batch_size = 10                          # default; CLI override via --pam-batch-size

    def __init__(self, host, admin_email, admin_password,
                 batch_size: int = 10,
                 debug_user_id: int | None = None):
        self.client = PamClient(host)
        self.batch_size = batch_size
        self._debug_user_id = debug_user_id
        self._memory_creation_sec: float = 0.0
        self._pam_user_id: int | None = None
        # ...

    async def setup(self, *, seed: int) -> None:
        await asyncio.to_thread(self.client.login, admin_email, admin_password)

    async def prepare_for_sample(self, sample: LoCoMoSample) -> None:
        # 1. Create per-sample user (or reuse if debug_user_id is set)
        # 2. Upload [(f"{sample_id}_conversation.json", bytes)]
        # 3. Trigger benchmark_memory pipeline; poll until terminal
        # 4. Record memory_creation_duration_sec into self.extras for the runner

    async def answer_batch(self, prompts: list[str]) -> list[BaselineResponse]:
        # 1. Render numbered prompt (Q1..QN → A1..AN)
        # 2. One SSE call via self.client.send_message
        # 3. Parse "An: ..." lines; distribute latency/injected_tokens evenly
        # 4. Output tokens via tiktoken per-answer (see §4.4)

    async def cleanup_sample(self) -> None:
        # delete_account (skipped when debug_user_id is set)

    async def teardown(self) -> None:
        pass

    def extras(self) -> dict:
        return {
            "memory_creation_duration_sec": self._memory_creation_sec,
            "pam_user_id": self._pam_user_id,
            "pam_batch_size": self.batch_size,
        }
```

### 4.4 Output-token estimation

`PamBaseline` estimates output tokens per parsed answer with `tiktoken.get_encoding("cl100k_base")` so the "output tokens" column in the report is populated for cross-baseline comparability. Comment in code reads simply:

```python
# Estimate output tokens with cl100k_base so the report shows a comparable
# value alongside other baselines. Pam does not expose the underlying LLM's
# token usage directly.
```

(No vendor names beyond the encoder id appear in code or docs.)

---

## 5. Existing files that change

| File | Change | Risk |
|---|---|---|
| `src/baselines/base.py` | Add `prepare_for_sample` / `cleanup_sample` / `answer_batch` (default no-ops / per-prompt fallback) + `external_memory: bool = False` + `batch_size: int = 1` + `injected_tokens` on `TokenUsage`. | Low — additive; LiteLLM continues to work. |
| `src/baselines/litellm_baseline.py` | Inherit defaults (explicit `external_memory = False`, `batch_size = 1`); no behavioral change. | None. |
| `src/registry.py` | Branch in `get_baseline()` for `name == "pam"`; add `"pam"` to `_BASELINE_ALIASES`. | Low. |
| `src/config.py` | Add `pam_batch_size: int = 10`, `pam_debug_user_id: int \| None = None`. | Low. |
| `src/cli.py` | Two new typer options (`--pam-batch-size`, `--pam-debug-user-id`); forward to `RunConfig`. | Low. |
| `src/tasks/locomo/pipeline.py` | Call `baseline.prepare_for_sample(sample)` / `cleanup_sample()`; branch on `external_memory` for prompt building; chunk by `batch_size` and call `answer_batch`; surface `baseline.extras()` to the runner. | Medium — touches the hot path. Covered by tests. |
| `src/tasks/locomo/prompts.py` | Add `build_bare_prompt(qa, seed)` — reuses cat-2 / cat-5 logic, skips conversation packing. | Low. |
| `src/runner.py` | Accept `extras` from the baseline at sample boundary and merge into the Mongo doc (`memory_creation_duration_sec` lands here for Pam, absent for LiteLLM). | Low. |
| `src/baselines/README.md` | Add "Pam baseline" section pointing at `src/baselines/pam/README.md`. | Doc only. |
| `.memory-bank/baselines/system-cards.md` | Add Pam system card (auth model, what gets uploaded, what `injected_tokens` means, why cost is 0, batching behavior). | Doc only. |
| `README.md` | One-line note in CLI surface table for the two new flags; add `PAM_API_HOST`/`PAM_API_USER`/`PAM_API_PASSWORD` to documented secrets. | Doc only. |
| `pyproject.toml` | Add `requests>=2.32`. | Low. |

No changes to evals, judge, Mongo schema (the new fields are additive), or report templates needed for M2 ship.

---

## 6. Tests (no live API calls — same rule as M1)

New tests in `tests/`:

1. **`test_pam_serialize.py`** — given a fixture `LoCoMoSample`, the serializer produces exactly one file named `<sample_id>_conversation.json` whose JSON content preserves session order and includes all `session_*` + `session_*_date_time` fields. Pure function, no Pam needed.
2. **`test_pam_baseline_lifecycle.py`** — replace `PamClient` with a stub (records call order). Drive the LoCoMo pipeline against a 25-question fixture with `batch_size=10`; assert call order is `login → prepare_for_sample → 3× send_message (10+10+5) → cleanup_sample → teardown`.
3. **`test_pam_batch_parser.py`** — feed `parse_batch_response` a synthetic Pam reply (`A1: foo\nA2: bar\n...`); assert correct splitting, including the partial-response / missing-Ai case.
4. **`test_pam_client_sse_parser.py`** — feed the SSE-stream parser a captured byte-stream and assert multi-turn / `injected_tokens` extraction works (port of the reference's behavior).
5. **`test_baseline_protocol_compat.py`** — `LiteLLMBaseline` still satisfies the `Baseline` protocol with the new optional hooks (regression).

No changes needed to existing tests (`qa_f1`, `llm_judge_schema`, etc.) because the new fields are additive.

---

## 7. Operational notes

- **Per-sample wall time.** Pam's memory build on a LoCoMo conversation is the big unknown — likely 3–10 min per sample based on the MemTrack pipeline. With 10 samples that's 30–100 min for memory alone, plus per-sample SSE: 200 questions / 10-per-batch × ~8 s = ~160 s of chat per sample. Estimated 1–2 hours per seed end-to-end.
- **Concurrency.** Single Pam backend → we keep the LoCoMo pipeline serial within a sample and serial across samples (matching M1). No cross-sample parallelism.
- **Cloud Run Jobs.** No infra changes. Adding `PAM_API_HOST` / `PAM_API_USER` / `PAM_API_PASSWORD` to the job (via Secret Manager or `--update-env-vars`) is a one-time setup. `run_job.sh` already forwards `--args` verbatim, so `--baseline pam --pam-batch-size 10` passes through.
- **Failure mode.** If memory creation fails for one sample, that sample is logged and skipped; remaining samples proceed. Matches the reference's per-config try/except. The Mongo doc for the failed sample carries an `error` field instead of metrics.
- **Cost (real money).** Zero LLM-token cost for Pam itself; the judge still costs (gpt-4o on ~2,000 LoCoMo questions ≈ a few dollars per seed).

---

## 8. What I'd build in what order (after approval)

1. Protocol + config + CLI plumbing (`base.py`, `config.py`, `cli.py`, `runner.py`) — small, no Pam needed.
2. `build_bare_prompt` + pipeline branch (external_memory + batch_size) — fully testable against LiteLLM with `--baseline gpt-4-turbo`.
3. `serialize.py` + `client.py` (ported from reference, sync, with Pam naming + tenacity, no `backup_workspace`).
4. `PamBaseline` + registry entry + batch parser.
5. Tests (all five files above).
6. Docs (system card, baseline README, README CLI table).
7. **Manual smoke run by you:** `--baseline pam --sample-index 0 --pam-batch-size 5`. I won't hit Pam from my side.

If this looks right, say "go" and I'll start with step 1.
