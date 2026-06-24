# MCP-Memory-on-Harness Benchmark — Design & Integration Plan

Status: **Shipped.** The first milestone (`claude-code` harness + `memory_md_mcp` backend on LoCoMo) is implemented — see `src/harnesses/claude_code/`, `src/baselines/mcp/`, and `scripts/run_mcp_benchmark.py`. Kept as the design record; later sections remain forward-looking.
Owner: Denys
Last updated: 2026-06-15

---

## 1. Goal

Add a **new experiment type** to `pam-benchmark`: evaluate **MCP memory baselines running on top of an agentic coding harness** (Claude Code first) on LoCoMo, so we can answer *"which memory approach works best when an agent like Claude Code is the runtime?"* and position **Pam** against the well-known, file-based memory baseline everyone recognizes.

Concretely, the first milestone is:

> Run **`--harness claude-code`** with **`--baseline memory_md_mcp`** on **LoCoMo**, end-to-end, writing the same per-sample columns to MongoDB as the Pam baseline does, with the ability to cap questions per conversation for debugging.

This must integrate cleanly with the existing harness (`src/runner.py`, `src/tasks/locomo/pipeline.py`, Mongo writer, reporting) and reuse — not duplicate — the Pam batching/retry/logging logic.

### Design intent (explicitly requested)

- **Harness abstraction** so adding **Codex** and **OpenClaw** later (and swapping base models) is a new class, not a rewrite.
- **MCP memory baseline abstraction** so adding **Supermemory** (and others) later is a new class.
- Running `claude-code + memory_md_mcp` on LoCoMo should *mirror* running Pam on LoCoMo: build memory from a conversation, then batch-answer questions, with retries, inter-batch sleep, logging, and Mongo parity — only the "how we talk to the system under test" differs (drive Claude Code instead of calling the Pam API).

---

## 2. Background: what the abstractions sit on top of

The current codebase already separates concerns we can reuse almost untouched:

- `src/runner.py` — orchestrates one `RunConfig`: loads dataset + task runner + baseline via `registry`, loops samples, calls the task runner, aggregates, writes Mongo + `metrics.json`. **Baseline-agnostic** except one `if cfg.baseline == "pam"` block that injects Pam kwargs.
- `src/tasks/locomo/pipeline.py::run_sample` — drives **any** `Baseline` through one sample: `prepare_for_sample` → chunk questions by `baseline.batch_size` → `answer_batch` → build `LoCoMoPrediction`s → `cleanup_sample`. Already handles `external_memory=True` (bare question prompts) and fires `on_question_done` / `on_batch_done`. **No changes needed.**
- `src/baselines/base.py` — the `Baseline` protocol + `BaselineBase` lifecycle (`setup`, `prepare_for_sample`, `answer`/`answer_batch`, `cleanup_sample`, `teardown`, `extras`, `baseline_kwargs_extra`) and `TokenUsage`/`BaselineResponse`. The Pam baseline is just one implementation.
- `src/baselines/pam/baseline.py` — reference implementation of the "external memory, batched Q/A, retry, inter-batch sleep, per-batch metrics, structured logging" pattern. Our new baseline copies this *shape*.
- `src/mongo.py` — one document per `(exp_name, sample_id, seed)` in `locomo_results`. Schema is just a dict; new baselines add fields freely.
- `src/registry.py` — `get_baseline` / `get_dataset` / `get_task_runner` name→object lookups.

**Key insight:** a "harness + MCP memory backend" is, from the harness's point of view, *just another `Baseline`*. If we implement it as one, the runner, pipeline, aggregation, Mongo, and reporting all work unchanged. The new code is: a **harness package**, an **mcp-memory-backend package**, a **composing baseline**, a thin **CLI + script**, and one **registry branch**.

---

## 3. Key decisions (LOCKED)

> **Decisions (2026-06-15):**
> - **3.1 → Option A**, native Claude Code file tools, **Obsidian-style Markdown** (YAML front-matter + `[[wikilinks]]`).
> - **3.2 → CLI** (`claude -p … --output-format json`) — more features, more popular. Hidden behind `ClaudeCodeHarness`.
> - **3.3 → `VERTEX_CREDENTIALS` is resolved by scheme:** a local path is used as-is; `gs://…` is downloaded; `sm://projects/<P>/secrets/<S>` is fetched from Secret Manager — then exported as `GOOGLE_APPLICATION_CREDENTIALS` only into the Claude Code subprocess. (Renamed from `GOOGLE_APPLICATION_CREDENTIALS` so Google's ADC doesn't try to load a `gs://`/`sm://` value as a file when fetching it.) **No `CLAUDE_CODE_HARNESS_MODEL` env var** — the base model is set **only** via `--harness-model`.
> - **3.4 → `injected_tokens` and `enriched_user_prompt_tokens` are `None`** for claude-code (Pam-only concepts), not `0`.
> - **§14: regional endpoint via `VERTEX_REGION`; non-cached input as `input_tokens` (cache split into `agent_cache_*`); re-add a cost column for harness experiments; keep per-sample memory only in debug mode, otherwise wipe; separate `scripts/run_mcp_benchmark.py`; ingestion is query-agnostic (never sees questions).**


### 3.1 What is `memory_md_mcp` — the markdown memory baseline?

**Requirement:** "claude-code stores its memory in `.md` files … the most popular way in AI research literature … a baseline everyone knows, implemented correctly."

**Finding from the literature.** The canonical, widely-recognized version of this is the **filesystem / markdown-notes memory** baseline — an agent that **writes plain Markdown notes during ingestion and retrieves them with file tools (read/grep) at query time**. It is the reference point in:

- Letta, *"Benchmarking AI Agent Memory: Is a Filesystem All You Need?"* — the standard framing that filesystem-as-memory is a strong, simple baseline (the MemGPT/Letta "memory blocks + external files" lineage). [letta.com/blog/benchmarking-ai-agent-memory](https://www.letta.com/blog/benchmarking-ai-agent-memory/)
- Mem0 (ECAI 2025), *"Building Production-Ready AI Agents with Scalable Long-Term Memory"* — establishes the head-to-head LoCoMo comparison protocol against file/RAG/full-context/OpenAI-Memory/Zep baselines; this is the methodology we mirror so our number is comparable. [arxiv.org/abs/2504.19413](https://arxiv.org/pdf/2504.19413)
- **Basic Memory** (`basicmachines-co/basic-memory`) — the most popular *MCP server* that persists agent memory as Obsidian-style Markdown files; the literal "markdown memory via MCP" product.

**Recommendation (decision needed):** implement `memory_md_mcp` as the **filesystem-markdown-memory** baseline behind our `McpMemoryBackend` interface, and pick **one** realization for M1:

- **Option A (recommended for M1): native Claude Code file tools.** Memory = a directory of `.md` notes the agent manages with built-in `Write`/`Edit`/`Read`/`Grep`. No third-party server, fully reproducible, controlled by *our* prompt protocol → "implemented correctly" is on us, not on someone else's server. This is exactly the "is a filesystem all you need" baseline.
- **Option B: Basic Memory MCP server.** A literal markdown-memory MCP server; more faithful to the word "mcp", but adds a dependency whose retrieval/correctness we don't control, and couples the baseline to a specific tool design.

Both satisfy the `McpMemoryBackend` interface; **Supermemory** later is the same interface with an HTTP/MCP server + API key. The interface is what makes "mcp baseline" swappable; whether M1 is realized via native tools or an external MCP server is an implementation detail of the `memory_md_mcp` backend.

> **For review:** Option A (native file tools, our protocol) vs Option B (Basic Memory MCP). I recommend **A** for M1 because "a baseline everyone knows, implemented correctly" is best served by a transparent, citable, reproducible protocol we fully control; we can add B/Basic-Memory as a second backend to show robustness.

We keep the name `memory_md_mcp` per your spec (the abstraction is "memory backend, optionally an MCP server").

### 3.2 How to drive Claude Code: Python SDK vs CLI subprocess

Claude Code can be driven headlessly two ways:

- **CLI:** `claude -p "<prompt>" --output-format json …` → parse JSON (`result`, token usage, cost, `session_id`, `num_turns`, `duration`).
- **Python SDK:** `claude-agent-sdk` (`query(prompt, options=ClaudeAgentOptions(...))`), typed result/usage objects, native async, MCP servers + allowed-tools as options, Vertex via env.

**Recommendation:** **Python SDK** behind our `Harness` interface (cleaner async, typed usage, no shell-quoting), with a **CLI-subprocess fallback** if the SDK's Vertex/MCP support is missing or pinned awkwardly. Decide during the M1 spike (§12). Either way it's hidden behind `ClaudeCodeHarness`, so the rest of the code doesn't care.

> ⚠️ **Verify during the spike, do not hard-code from this doc:** exact flag/option names (`--mcp-config`, `--allowedTools`, `--permission-mode`, `--add-dir`, `--max-turns`, output JSON field names) and the Vertex region env var. The reference gathered (below) is mostly right but some flags may differ by installed version — confirm against `claude --help` / the SDK's `ClaudeAgentOptions` on the pinned version.

### 3.3 Claude Code auth on GCP Vertex (what we'll use)

Run official Claude Code against Claude on **Vertex AI** using the service-account key `pam-agent-credentials.json`. Env the harness sets before each invocation:

```
CLAUDE_CODE_USE_VERTEX=1
ANTHROPIC_VERTEX_PROJECT_ID=<gcp-project>
GOOGLE_APPLICATION_CREDENTIALS=<abs path to pam-agent-credentials.json>
CLOUD_ML_REGION=<region>            # verify: some docs use ANTHROPIC_VERTEX_REGION / "global"
ANTHROPIC_MODEL=<vertex model id>   # or pass --model / options.model
```

New secrets in `secrets.env` (gitignored; you add the values):
```
VERTEX_PROJECT_ID=...
VERTEX_REGION=...                                  # regional endpoint, e.g. us-east5
VERTEX_CREDENTIALS=/abs/path/creds.json            # OR gs://bucket/creds.json OR sm://projects/<P>/secrets/<S>[/versions/<V>]
```
The base model is supplied **only** via `--harness-model` (no env var). The harness (`claude_code/auth.py`) maps these to the env Claude Code expects (`ANTHROPIC_VERTEX_PROJECT_ID`, `CLOUD_ML_REGION`, and the resolved local path as `GOOGLE_APPLICATION_CREDENTIALS`) per invocation. **Credential resolution by scheme** (input var = `VERTEX_CREDENTIALS`): a local path is used as-is (resolved to absolute); a `gs://bucket/key` URI is downloaded; an `sm://projects/<P>/secrets/<S>[/versions/<V>]` reference is fetched from Secret Manager (payload = the key JSON as text). `gs://`/`sm://` are written to a local temp file (cached for the process) since Claude Code expects a local path. The input var is deliberately *not* named `GOOGLE_APPLICATION_CREDENTIALS` — that reserved name would make Google's ADC try to load a `gs://`/`sm://` value as a file when we fetch it (so Secret Manager access cleanly uses the runtime service account). No project/secret id is hardcoded — the `sm://` value is whatever you put in `secrets.env` (safe for a public release). Token usage and cost are still reported in the JSON output under Vertex, so we get real `input/output/cache` tokens — unlike Pam where input is hidden.

### 3.4 Token/usage mapping to the existing Mongo columns

Unlike Pam (the model's input is hidden, so we synthesize), **Claude Code reports real usage per invocation**. One `answer_batch` = one Claude Code run answering the whole batch = one usage record. Proposed mapping so the existing report "just works" (and the per-sample token table is meaningful):

| Mongo per-question field | Source from Claude Code run (distributed evenly across the batch via the existing `_distribute`) |
|---|---|
| `input_tokens` | non-cached input tokens for the batch run |
| `output_tokens` | output tokens |
| `prompt_tokens` | tokens of the rendered `Q1..QN` prompt **we** sent (counted locally, like Pam) |
| `context_tokens` | `input_tokens - prompt_tokens` (the memory/system/tool context the agent pulled in) via `split_input_tokens` |
| `agent_cache_read_tokens` | `cache_read_input_tokens` |
| `agent_cache_write_tokens` | `cache_creation_input_tokens` |
| `agent_input_tokens` / `agent_output_tokens` | mirror input/output (the harness *is* the agent) |
| `est_cost_usd` | `total_cost_usd` (real; Pam's is 0) |
| `latency_ms` | batch `duration` / N |
| `injected_tokens`, `enriched_user_prompt_tokens` | **`None`** (Pam-specific concepts; not applicable to claude-code) |

`None` for those two requires making the fields `int | None` on `TokenUsage`/`LoCoMoPrediction` and a None-safe aggregation (`total_enriched_user_prompt_tokens` = `None` when every value is `None`, else the sum). Pam keeps writing ints, so its docs/reporting are unchanged.

`memory_creation_duration_sec` = the wall-clock of the ingestion (memory-build) Claude Code invocation, stored exactly like Pam's. Memory-build tokens/cost go into `extras` (not the per-question totals).

Because the baseline name is `memory_md_mcp` (not `"pam"`), the report's existing non-Pam branches already use `total_input_tokens` and `total_context_tokens` correctly — no reporting changes required. (We'll double-check the "Avg Input/Context" Pam-special-casing only triggers for `baseline == "pam"`.)

---

## 4. Target architecture

New packages (additive; nothing existing is restructured):

```
src/
  harnesses/                      # NEW — agentic runtimes
    __init__.py
    base.py                       # Harness protocol + HarnessResult + registry helper
    claude_code/
      __init__.py
      harness.py                  # ClaudeCodeHarness (SDK or CLI subprocess)
      auth.py                     # Vertex env setup from secrets
    # future: codex/harness.py, openclaw/harness.py
  baselines/
    mcp/                          # NEW — MCP memory baselines that run ON a harness
      __init__.py
      base.py                     # McpMemoryBackend protocol + McpHarnessBaseline (composes harness+backend)
      memory_md/
        __init__.py
        backend.py                # memory_md_mcp backend (markdown filesystem memory)
        prompts.py                # ingest + answer prompt protocol for markdown memory
      # future: supermemory/backend.py
  batch_protocol.py               # NEW (refactor) — shared batch render/parse/distribute/retry helpers
                                  #   extracted from pam/baseline.py; reused by Pam + McpHarnessBaseline
scripts/
  run_mcp_benchmark.py            # NEW — entry point (mirrors run_benchmark.py)
src/
  mcp_cli.py                      # NEW — typer CLI for the MCP-harness experiment
```

Changed (small, additive):
- `src/config.py` — add optional `harness`, `harness_model`, and mcp-experiment knobs to `RunConfig`.
- `src/registry.py` — `get_baseline` learns the `memory_md_mcp` family; add `get_harness(name, model=...)`.
- `src/runner.py` — generalize the one `if cfg.baseline == "pam"` block into a small baseline-kwargs assembler that also handles harness baselines (or branch on `cfg.harness`).
- `src/baselines/pam/baseline.py` — import the shared helpers from `batch_protocol.py` instead of local copies (behavior identical; keeps one source of truth).

### Composition

```
McpHarnessBaseline(BaselineBase)         # IS-A Baseline → plugs into run_sample unchanged
  ├── harness:  Harness                  # e.g. ClaudeCodeHarness(model=...)
  └── backend:  McpMemoryBackend         # e.g. MemoryMdBackend()
```

`run_sample` calls the baseline; the baseline orchestrates `harness.run(...)` with the MCP servers / allowed-tools / prompts that `backend` defines, against a per-sample memory directory.

---

## 5. Interfaces

### 5.1 `Harness` (src/harnesses/base.py)

```python
@dataclass
class HarnessResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    duration_ms: float = 0.0
    session_id: str | None = None
    num_turns: int = 0
    raw: dict = field(default_factory=dict)

class Harness(Protocol):
    name: str                      # "claude-code"
    model: str | None              # base model id (overridable per run)

    async def setup(self) -> None: ...        # auth/env/binary checks
    async def run(
        self, *,
        prompt: str,
        working_dir: Path,                     # the agent's cwd (memory lives here)
        mcp_servers: dict | None = None,       # backend-supplied MCP config
        allowed_tools: list[str] | None = None,
        system: str | None = None,
        max_turns: int | None = None,
        timeout_sec: float | None = None,
    ) -> HarnessResult: ...
    async def teardown(self) -> None: ...
```

`ClaudeCodeHarness` implements `run` via the SDK (or CLI), setting Vertex env from `auth.py`, mapping the JSON usage into `HarnessResult`. Codex/OpenClaw are future `Harness` implementations with the same contract and their own model handling.

### 5.2 `McpMemoryBackend` (src/baselines/mcp/base.py)

Defines *how a harness stores and recalls memory* — independent of which harness:

```python
class McpMemoryBackend(Protocol):
    name: str                                  # "memory_md_mcp"

    def mcp_servers(self, memory_dir: Path) -> dict | None: ...   # None ⇒ native file tools
    def allowed_tools(self) -> list[str]: ...                      # e.g. ["Read","Write","Edit","Grep"]
    def ingest_prompt(self, conversation_text: str) -> str: ...    # build memory from a conversation
    def answer_prompt(self, batch_prompt: str) -> str: ...         # answer Q1..QN using memory (read-only)
    async def setup(self) -> None: ...
    async def reset(self, memory_dir: Path) -> None: ...           # clear memory for a fresh sample
```

`MemoryMdBackend` (the `memory_md_mcp` baseline): native file tools (Option A) or Basic Memory MCP (Option B). Supermemory later: returns its MCP server config + API-key env, with allowed tools `mcp__supermemory__*`.

### 5.3 `McpHarnessBaseline` (src/baselines/mcp/base.py)

A `BaselineBase` that mirrors `PamBaseline` 1:1 in *lifecycle shape* (so reviewers can diff them):

- `external_memory = True`, `batch_size`, and the same tunables: `INTER_BATCH_SLEEP_SEC`, `MAX_BATCH_RETRIES`, `BATCH_RETRY_BASE_SLEEP_SEC`.
- `setup()` → `harness.setup()` + `backend.setup()`.
- `prepare_for_sample(sample)`:
  - compute `memory_dir = outputs/<EXP>/<HARNESS>/<SEED>/<sample_id>/memory/` (created); reset batch counters.
  - serialize the conversation to readable text (reuse `pam/serialize.py` logic or a new `mcp/serialize.py` producing a transcript the agent ingests).
  - **build memory**: `harness.run(prompt=backend.ingest_prompt(transcript), working_dir=memory_dir, mcp_servers=backend.mcp_servers(memory_dir), allowed_tools=backend.allowed_tools())`; time it → `memory_creation_duration_sec`; record build usage in `extras`.
  - debug mode: `--mcp-debug-sample-dir` / reuse — skip build if a prior memory dir exists (analogous to `--pam-debug-user-id`).
- `answer_batch(prompts)`: **identical control flow to Pam** via the shared `batch_protocol` helpers — render `Q1..QN`, increment/log `batch i/N`, inter-batch sleep, send (here: `harness.run(answer_prompt, read-only tools)`), parse `A1..AN`, **retry up to 2× with exponential backoff when 0 answered**, distribute usage across questions, build `BaselineResponse`s. Log line: `Claude Code answered X/N questions in batch i/M for sample=<id> (… ms)`.
- `cleanup_sample()`: keep memory on disk by default (it lives under `outputs/` for inspection / debug reuse); optional `--mcp-delete-memory` to wipe.
- `extras()` → `harness`, `harness_model`, `memory_backend`, `memory_dir`, `memory_creation_duration_sec`, build tokens/cost, session ids.
- `baseline_kwargs_extra()` → `{"harness":…, "harness_model":…, "memory_backend":…}` (lands in the Mongo doc's `baseline_kwargs`, like Pam's `agent_model_used`).

### 5.4 Shared refactor: `src/batch_protocol.py`

Extract from `pam/baseline.py` (no behavior change) so both baselines share one implementation:
`_render_batch_prompt`, `parse_batch_response`, `_strip_reasoning_scaffold`, `_distribute`, and the retry/answered-count helper. Pam imports from here; the new baseline imports the same. This is the single biggest anti-duplication lever and should land first.

---

## 6. The `memory_md_mcp` backend (Option A reference design)

A transparent, citable markdown-memory protocol (we control correctness):

- **Memory layout** under `memory_dir`:
  - `memory/index.md` — table of contents / entity index the agent maintains.
  - `memory/notes/*.md` — one note per topic/entity/session, structured (front-matter + bullet facts with dates), Obsidian/Basic-Memory-compatible so Option B is a drop-in.
- **Ingest prompt** (build phase): instruct the agent to read the conversation transcript and **write durable, atomic, dated facts** into markdown notes (one note per salient entity/topic), plus maintain `index.md`. No question is shown during ingestion (memory must be query-agnostic — important for a fair baseline; otherwise it's retrieval-with-oracle).
- **Answer prompt** (query phase): a **read-only** invocation (`Read`/`Grep` only) that recalls from the markdown notes and answers the numbered `Q1..QN` batch in the exact `A1..AN` format the shared parser expects. The agent searches/reads notes itself (this is the "filesystem memory" recall).
- **Correctness guardrails** (so it's a legitimate baseline):
  - ingestion sees the conversation **only**, never the questions;
  - answering sees the questions + memory **only**, never the raw conversation;
  - fixed model + temperature; deterministic prompts; per-sample isolated memory dir;
  - same numbered-batch answer protocol, retries, and scoring as Pam → apples-to-apples.

Cite the design in the system card (Letta filesystem-memory framing + Basic Memory format + Mem0 LoCoMo protocol) so the baseline is defensible.

---

## 7. CLI / config / script

### `RunConfig` additions (`src/config.py`, all optional, default None/False)
```python
harness: str | None = None              # "claude-code" (None ⇒ classic API/LiteLLM run)
harness_model: str | None = None        # base model id for the harness
mcp_batch_size: int = 10                # questions per batch (mirror pam_batch_size)
mcp_debug_sample: str | None = None     # reuse an existing memory dir (debug)
mcp_delete_memory: bool = False         # wipe memory after each sample
```
`max_questions`, `seed`, `sample_index`, `save_responses`, `mongo`, `judge_*`, `output_dir` are reused as-is (debug-cap requirement satisfied by existing `--max-questions`).

### `scripts/run_mcp_benchmark.py`
Thin entry (like `run_benchmark.py`): add `src/` to path, delegate to `mcp_cli.app`. Usage:
```
uv run python scripts/run_mcp_benchmark.py \
  --dataset locomo --harness claude-code --baseline memory_md_mcp \
  --harness-model <vertex-model-id> --exp-name mcp_locomo_md_v1 \
  --mcp-batch-size 10 --max-questions 20      # debug cap
```

### `src/mcp_cli.py`
A typer command that builds the **same `RunConfig`** and calls `runner.run(cfg)`. New flags: `--harness`, `--harness-model`, `--mcp-batch-size`, `--mcp-debug-sample`, `--mcp-delete-memory`. (We keep it a *separate* CLI/script so the two experiment types stay legible, but they share `RunConfig` + `runner.run`.)

### `registry.py`
- `get_harness(name, model=None)` → `ClaudeCodeHarness(model=...)` (extensible).
- `get_baseline("memory_md_mcp", harness=..., harness_model=..., **kw)` → `McpHarnessBaseline(harness=get_harness(...), backend=MemoryMdBackend(), batch_size=..., …)`.

### `runner.py`
Replace the single `if cfg.baseline == "pam"` kwargs block with: if `cfg.harness` set → assemble harness-baseline kwargs (`harness`, `harness_model`, `batch_size=cfg.mcp_batch_size`, memory-dir root from `outputs/<exp>/<harness>/<seed>`, debug/delete flags); elif `cfg.baseline == "pam"` → existing Pam block. Everything downstream (aggregate, qa_responses, Mongo write) is unchanged.

---

## 8. Output & storage layout

Memory persists exactly where requested:
```
outputs/<EXP_NAME>/<HARNESS_NAME>/<SEED>/<sample_id>/memory/{index.md, notes/*.md}
outputs/<EXP_NAME>/<HARNESS_NAME>/<SEED>/config.yaml
outputs/<EXP_NAME>/<HARNESS_NAME>/<SEED>/metrics.json
outputs/<EXP_NAME>/<HARNESS_NAME>/<SEED>/responses.log     # when --save-responses
```
Note: classic runs use `outputs/<exp>/<seed>/`; harness runs insert `<HARNESS_NAME>/` so multiple harnesses under one experiment don't collide. `runner.resolved_output_dir()` gets a harness-aware variant when `cfg.harness` is set.

---

## 9. Mongo parity

Same collection (`locomo_results`), same document shape as Pam, so existing dashboards/reports work:
- identity: `exp_name`, `sample_id`, `sample_index`, `seed`, `baseline="memory_md_mcp"`, `baseline_kwargs={harness, harness_model, memory_backend}`, `dataset_name`, `task_name`.
- aggregates: `total_questions`, accuracy/judge fields, `total_input_tokens`, `total_output_tokens`, `total_prompt_tokens`, `total_context_tokens`, `total_agent_cache_read_tokens`, `total_agent_cache_write_tokens`, `total_cost_usd`, latency percentiles, `memory_creation_duration_sec`, `execution_time_seconds`.
- `qa_responses[]`: every per-question field Pam writes (token mapping per §3.4).
We add `harness` / `harness_model` / `memory_backend` (inside `baseline_kwargs`) for grouping in queries and reports.

---

## 10. Logging (mirror Pam)

- build: `Claude Code built memory for sample=<id> in <s>s (notes=<k>, model=<m>)`.
- per batch (success): `Claude Code answered X/N questions in batch i/M for sample=<id> (<ms> ms, cost=$<…>)`.
- 0-answer retry: `Claude Code batch i/M got 0/N answers; retry k/2 after <s>s`.
- failure: `Claude Code run failed for batch i/M (N questions), attempt k/3: <err>`.
- structured `--log-format json` works as-is.

---

## 11. Reuse vs. new (anti-duplication summary)

| Concern | Reused as-is | New |
|---|---|---|
| Sample loop, aggregation, Mongo, metrics.json | `runner.py` | small kwargs branch |
| Per-sample drive (prepare→batch→cleanup), prompt build, batching, `on_batch_done` | `tasks/locomo/pipeline.py`, `prompts.py` | — |
| Batch render/parse/distribute/retry | — | `batch_protocol.py` (extracted from Pam, shared) |
| Scoring (F1 + judge), reporting | `evals/*`, `reporting/*` | — |
| Baseline lifecycle contract | `baselines/base.py` | `McpHarnessBaseline` |
| Talking to the system under test | — | `harnesses/*` + `baselines/mcp/*` |

---

## 12. Milestones

- **M0 — Spike (1–2 days, no integration).** Stand up `ClaudeCodeHarness.run` against Vertex with `pam-agent-credentials.json`; confirm: headless invocation works, JSON usage/cost parse correctly, MCP/allowed-tools/working-dir behave, a second invocation in the same dir sees files the first wrote. **Lock the exact SDK/CLI flags + Vertex region var here** (resolves §3.2/§3.3 unknowns). Decide SDK vs CLI.
- **M1 — `claude-code` + `memory_md_mcp` on LoCoMo (the target).** Extract `batch_protocol.py`; build `harnesses/claude_code`, `baselines/mcp/memory_md`, `McpHarnessBaseline`, CLI + script + registry + config; per-sample markdown memory under `outputs/<EXP>/<HARNESS>/<SEED>/…`; batched answering with retry/sleep/logging; Mongo parity; debuggable with `--max-questions`. **Acceptance:** a small `--max-questions 20` run over ≥1 sample produces a Mongo doc with the same columns as a Pam doc and a populated memory dir; a full run completes.
- **M2 — Abstraction proof.** Add a second `McpMemoryBackend` (Basic Memory MCP **or** Supermemory) to prove the backend interface; document parity.
- **M3 — Second harness.** Add `CodexHarness` (or `OpenClawHarness`) to prove the `Harness` interface + base-model swap.

---

## 13. Testing strategy

- Unit: `batch_protocol` (already covered for Pam; reuse), `HarnessResult` usage mapping, `MemoryMdBackend` prompt/tool config, `McpHarnessBaseline` lifecycle with a **fake harness** (records calls, returns canned `A1..AN`) — mirroring `tests/baselines/pam/` (stub client + autouse fixture zeroing sleeps/retries).
- The fake harness lets us test build→batch→retry→Mongo-field mapping with **no Claude Code / network** (fast CI), exactly like the Pam stub tests.
- A separate, opt-in (env-gated) live smoke test that actually invokes Claude Code on Vertex over one tiny sample (`--max-questions 4`).

---

## 14. Open questions / decisions — RESOLVED

**Resolved 2026-06-15:** (1) Option A native file tools, Obsidian markdown. (2) CLI. (3) regional endpoint, `VERTEX_REGION`; default model only via `--harness-model`. (4) recommended (non-cached `input_tokens`, cache → `agent_cache_*`). (5) yes — re-add a cost column for harness experiments. (6) keep per-sample memory only when a debug flag is set, otherwise wipe after the sample. (7) separate `scripts/run_mcp_benchmark.py`. (8) yes — ingestion is query-agnostic.

Original list (for the record):

1. **`memory_md_mcp` realization:** Option A (native file tools, our protocol — recommended) vs Option B (Basic Memory MCP server). (§3.1)
2. **Drive Claude Code:** Python SDK (recommended) vs CLI subprocess. (§3.2)
3. **Vertex region var** name/value (`CLOUD_ML_REGION` vs `ANTHROPIC_VERTEX_REGION`, regional vs `global`) and which Claude model id on Vertex is the default base model. (§3.3)
4. **`input_tokens` semantics** for the report's "Avg Input" — use non-cached input only, or input+cache-read? (§3.4) Recommend non-cached input as `input_tokens`, cache split into `agent_cache_*`.
5. **Cost in report:** cost is currently hidden in the report but stored. Claude Code gives *real* cost — do we want a cost column back for harness experiments? (separate small change if yes)
6. **Memory retention:** keep per-sample memory dirs after the run (default, for inspection/debug-reuse) vs wipe.
7. **Separate CLI/script** (`run_mcp_benchmark.py`, recommended for legibility) vs folding `--harness` into the existing `run_benchmark.py`.
8. **Ingestion fairness:** confirm ingestion never sees questions (query-agnostic memory) — required for a defensible baseline.

---

## 15. Risks

- **Claude Code flag/SDK drift** — mitigated by the M0 spike locking exact names against the installed version; everything hidden behind `Harness`.
- **Non-determinism / cost / latency** — agentic runs are slower and pricier than a single API call; the inter-batch sleep + retries compound this. Use `--max-questions` for debugging; budget full runs. Consider `--max-turns` to bound agent loops.
- **Baseline legitimacy** — if ingestion or recall is sloppy (e.g., memory sees questions, or recall reads the raw transcript), the number is not comparable. §6 guardrails + system-card citation address this; flag for review.
- **Vertex model availability per region** — verify the chosen model is enabled in the chosen region for `pam-agent-credentials.json`'s project.
- **Output dir collisions** — the `<HARNESS_NAME>` path segment prevents multi-harness clashes; confirm `resolved_output_dir` is updated.

---

## 16. File-by-file change list (for the eventual PR)

**New**
- `src/harnesses/{__init__,base}.py`, `src/harnesses/claude_code/{__init__,harness,auth}.py`
- `src/baselines/mcp/{__init__,base}.py`, `src/baselines/mcp/memory_md/{__init__,backend,prompts}.py`
- `src/baselines/mcp/serialize.py` (or reuse Pam's)
- `src/batch_protocol.py` (extracted shared helpers)
- `src/mcp_cli.py`, `scripts/run_mcp_benchmark.py`
- `tests/harnesses/…`, `tests/baselines/mcp/…` (+ fake-harness conftest)
- `.memory-bank/baselines/system-cards.md` — add a `memory_md_mcp` (filesystem markdown memory) system card with citations

**Changed**
- `src/config.py` (RunConfig additions), `src/registry.py` (`get_harness`, baseline branch), `src/runner.py` (kwargs branch + harness-aware output dir), `src/baselines/pam/baseline.py` (import shared helpers from `batch_protocol`), `README.md` / `src/baselines/*/README.md` (new env vars + experiment usage)

---

## 17. Sources

- Letta — *Benchmarking AI Agent Memory: Is a Filesystem All You Need?* — https://www.letta.com/blog/benchmarking-ai-agent-memory/
- Mem0 (ECAI 2025) — *Building Production-Ready AI Agents with Scalable Long-Term Memory* — https://arxiv.org/pdf/2504.19413
- Basic Memory (markdown-file MCP memory server) — `basicmachines-co/basic-memory`
- LoCoMo (ACL 2024, Maharana et al.) — long-term conversational memory benchmark (see `docs/blog_post_notes_locomo.md`)
- Claude Code headless / MCP / Vertex mechanics — gathered via claude-code-guide; **flag names to be confirmed during the M0 spike**.
