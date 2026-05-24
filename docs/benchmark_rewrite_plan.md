# PAM Benchmark — Rewrite & Architecture Plan

Status: **Draft for review** — no code has been written yet.
Owner: Denys
Last updated: 2026-05-23

---

## 1. Goal

Rewrite the `pam-benchmark` repo into a clean, library-first benchmark whose primary purpose is to compare **our memory solution (PAM)** against competing memory products and simple LLM baselines on memory-oriented datasets (LoCoMo, BEAM, DRBench, LongMemEval, MEMTRACK, MemoryAgentBench).

The methodology follows the standards in `docs/init_memory_bank.md` (datasheets, system cards, multi-seed runs, statistical reporting, reproducibility) so that any number we publish internally or externally is defensible — but the codebase is **not** structured around an academic submission.

## 2. Constraints & Principles

- **Library, not framework.** Reuse popular Python libraries (LiteLLM, HF datasets, tiktoken, tenacity, pydantic, instructor, rank-bm25, sentence-transformers, faiss-cpu, rich, typer, pandas, scipy.stats). Avoid bespoke abstractions where a library exists.
- **Drop Harbor.** Harbor coupled task definition, container build, and execution. We replace it with: plain Python + a single Dockerfile + `scripts/run_benchmark.py`.
- **Per-task independence.** Adding a new dataset must not require editing code in any other dataset/task. Only `src/evals/` and `src/utils/` are shared.
- **Unified evaluation.** Evaluation metrics (LLM-as-judge, token efficiency, runtime) live in `src/evals/` and are reused identically across datasets and baselines.
- **Reproducibility first.** Pinned `uv.lock`, container digest, seeds, dispersion, and significance for every reported comparison (per `init_memory_bank.md` `reproducibility/` standards).
- **Two execution targets.** Same code must run on **GCP Cloud Run Jobs** (production scale) and **locally** (development/iteration).
- **Visible progress.** Rich-based progress logging so a long run is readable in real time, both locally and in Cloud Run logs.
- **Mongo is the source of truth** for results; local JSON is a side artifact.

## 3. Scope of Milestone 1

> Evaluate `gpt-4-turbo` on the **LoCoMo** dataset end-to-end on the new architecture.

Everything else (other datasets, other baselines, retrieval, HTML report polish) is out of scope for M1. M1 is the vertical slice that proves the architecture.

What ships in M1:
- New folder layout (described in §5).
- `uv` + `pyproject.toml` with the library stack.
- `Dockerfile` runnable both locally and on Cloud Run Jobs.
- `scripts/run_benchmark.py` typer CLI with all flags wired.
- `src/datasets/locomo/` loader.
- `src/baselines/litellm_baseline.py` (gpt-4-turbo via LiteLLM).
- `src/tasks/locomo/` pipeline + prompts + instruction.md.
- `src/evals/qa_f1.py` (LoCoMo's native F1) + `llm_judge.py` (rubric judge).
- Mongo writer parity with current `locomo_results` schema.
- Rich progress + structured logs.
- `scripts/generate_report.py` (extracted from `src/tasks/locomo/generate_report.py`).
- Rewritten `README.md` and `src/tasks/locomo/instruction.md`.
- `.memory-bank/` populated per `docs/init_memory_bank.md`.

What is **deferred**:
- BEAM, DRBench, LongMemEval, MEMTRACK, MemoryAgentBench datasets.
- PAM, Honcho, Supermemory, mem0, Zep, Claude Code + Memory.md / Obsidian, OpenClaw baselines.
- Retrieval / RAG baselines (rank-bm25, sentence-transformers, faiss).
- Multi-seed statistical significance (single seed for M1; framework supports ≥3 seeds from day one but we don't run them yet).
- Cost / latency dashboards.

## 4. What we remove from the old layout

| Path | Action | Reason |
|---|---|---|
| `src/tasks/locomo/tests/` | Delete | Harbor-specific verification; not used in new flow |
| `src/tasks/locomo/solution/` | Delete | Harbor entry script; replaced by `scripts/run_benchmark.py` |
| `src/tasks/locomo/environment/Dockerfile` | Delete | Single project-root `Dockerfile` instead |
| `src/tasks/locomo/environment/docker-compose.yaml` | Delete | Not needed; Cloud Run Jobs has no compose |
| `src/tasks/locomo/environment/requirements.txt` | Delete | Replaced by `pyproject.toml` + `uv.lock` |
| `src/tasks/locomo/environment/pam_*.sh`, `run_pam_locomo.sh` | Delete from M1 scope | PAM baseline deferred to M2+ |
| `src/tasks/locomo/environment/INIT.md`, `INTRO_TEMPLATE.md`, `init.py`, `pam_utils.py`, `pam_evaluate.py` | Delete | PAM agent files; out of M1 scope. Git history preserves them for the M2 PAM port. (`CLAUDE.md` already removed manually.) |
| `src/tasks/locomo/environment/task_eval/{gpt,claude,gemini,hf_llm}_utils.py` | Delete | Replaced by `LiteLLMBaseline` + per-task prompt code |
| `src/tasks/locomo/environment/task_eval/{evaluate_qa,evaluation,evaluation_stats}.py` | Port logic into `src/evals/qa_f1.py` and `src/evals/stats.py` | Keep the F1 math, drop the harness |
| `src/tasks/locomo/environment/task_eval/{get_facts,get_session_summaries,rag_utils}.py` | Defer to retrieval milestone | Not needed for M1 |
| `src/tasks/locomo/environment/global_methods.py` | Replace with `src/utils/llm.py` (LiteLLM-based) | Centralized model access |
| `src/tasks/locomo/environment/run_locomo.py` | Replace with `src/tasks/locomo/pipeline.py` | Restructured |
| `src/tasks/locomo/generate_report.py` (40 KB) | Split: pure functions → `src/reporting/`; entry point → `scripts/generate_report.py` | Per user instruction |
| `src/tasks/locomo/instruction.md` | Rewrite | Reflect new run model |
| `src/tasks/locomo/environment/prompt_examples/` | Move to `src/tasks/locomo/prompt_examples/` | Keep |
| `src/agents/` (empty) | Rename to `src/baselines/` | Matches naming we adopted in `init_memory_bank.md` |
| `src/datasets/longmemeval/`, `src/datasets/memtrack/` | Keep folder skeletons; loaders deferred | M2+ |
| `src/tasks/longmemeval/`, `src/tasks/memtrack/` | Create empty skeletons with `README.md` only | Make the slot visible for future work |
| `bench_venv/`, `venv/` | Delete from repo (already gitignored?) | Replaced by `uv` |
| `reports/` (top-level) | Move under `reports/` still, but gitignored; generated only | No source content there |

## 5. Target folder structure

```
pam-benchmark/
├── .dockerignore                    # at root so it applies to the build context
├── pyproject.toml                   # uv-managed
├── uv.lock
├── .python-version
├── README.md                        # rewritten in M1
├── secrets.env                      # gitignored
├── cluster/                         # everything needed to run on a remote cluster
│   ├── Dockerfile                   # single image; runs locally + Cloud Run Jobs
│   ├── deploy.sh                    # build + push + `gcloud run jobs deploy`
│   └── run_job.sh                   # `gcloud run jobs execute` with arg forwarding
├── docs/
│   ├── init_memory_bank.md
│   └── benchmark_rewrite_plan.md    # this file
├── .memory-bank/                    # populated in M1 per init_memory_bank.md
├── scripts/                         # Python entrypoints; all accept --exp-name
│   ├── run_benchmark.py             # typer entry; the only benchmark-run entrypoint
│   ├── generate_report.py           # pulls Mongo rows for an --exp-name, renders HTML
│   └── download_data.py             # idempotent dataset download + checksum (no --exp-name)
├── src/                             # PYTHONPATH=src; no wrapper package
│   ├── cli.py                       # typer app (imported by scripts/run_benchmark.py)
│   ├── config.py                    # pydantic RunConfig
│   ├── registry.py                  # name → (dataset, task, baseline) lookup
│   ├── runner.py                    # orchestrates one (dataset, task, baseline, seed) run
│   ├── progress.py                  # rich progress wrappers
│   ├── logging.py                   # structured logger setup
│   ├── env.py                       # secrets.env / Secret Manager loading
│   ├── mongo.py                     # MongoDB writer + schemas
│   ├── seeds.py                     # seed_all() across random/numpy/torch
│   ├── datasets/                    # NOTE: shadows HF `datasets` lib; see §13
│   │   ├── __init__.py
│   │   ├── base.py                  # DatasetLoader protocol
│   │   ├── locomo/
│   │   │   ├── __init__.py
│   │   │   ├── loader.py            # LoCoMoLoader (custom JSON loader for M1)
│   │   │   ├── schemas.py           # pydantic: LoCoMoSample, LoCoMoQA
│   │   │   ├── data/                # locomo10.json (gitignored, downloaded)
│   │   │   └── README.md
│   │   ├── longmemeval/             # M2+; folder + README only
│   │   └── memtrack/                # M2+; folder + README only
│   ├── baselines/                   # renamed from src/agents/
│   │   ├── __init__.py
│   │   ├── base.py                  # Baseline protocol (generate(prompt) -> Response)
│   │   ├── litellm_baseline.py      # used for gpt-4-turbo, claude, gemini, etc.
│   │   └── README.md                # how to add a baseline
│   ├── tasks/
│   │   ├── __init__.py
│   │   ├── locomo/
│   │   │   ├── __init__.py
│   │   │   ├── pipeline.py          # load sample → build prompt → call baseline → collect predictions
│   │   │   ├── prompts.py           # LoCoMo-specific prompt templates
│   │   │   ├── prompt_examples/     # moved from old environment/
│   │   │   ├── instruction.md       # rewritten in M1
│   │   │   └── README.md
│   │   ├── longmemeval/             # M2+; README only
│   │   └── memtrack/                # M2+; README only
│   ├── evals/
│   │   ├── __init__.py
│   │   ├── base.py                  # Evaluator protocol
│   │   ├── qa_f1.py                 # token F1 (LoCoMo native)
│   │   ├── llm_judge.py             # litellm + instructor + pydantic rubric
│   │   ├── efficiency.py            # tiktoken-based token counts; cost estimation
│   │   ├── runtime.py               # wall-clock timing helpers
│   │   └── stats.py                 # bootstrap CI, paired bootstrap test (M2+ usage)
│   ├── reporting/
│   │   ├── __init__.py
│   │   ├── query.py                 # pull rows from Mongo for an experiment
│   │   ├── html.py                  # render HTML report
│   │   ├── markdown.py              # render Markdown summary
│   │   └── templates/               # Jinja2 templates
│   └── utils/
│       ├── __init__.py
│       ├── llm.py                   # LiteLLM completion wrapper: retries, rate limit, token counts
│       ├── io.py                    # JSON/JSONL helpers, checksums
│       └── timing.py                # context manager for timed blocks
├── tests/                           # minimal unit tests for evals + utils only
│   ├── test_qa_f1.py
│   └── test_llm_judge_schema.py
└── reports/                         # gitignored; generated HTML
```

Key naming decisions to confirm in §13:
- No wrapper package: `src/` is on `PYTHONPATH`; subdirs (`datasets`, `tasks`, `evals`, `baselines`, `reporting`, `utils`) are top-level importable modules. The project is a uv-managed **application** (not a pip-installable library), so no build backend or wrapper package is needed.
- `baselines/` (not `agents/`, not `systems-under-test/`) — consistent with the renamed memory-bank section. Existing empty `src/agents/` is renamed.
- `src/datasets/` shadows the HF `datasets` library when `PYTHONPATH=src`. M1 sidesteps this by writing a custom JSON loader for LoCoMo and not depending on HF `datasets`. See §13 for the longer-term decision.

## 6. Component design

### 6.1 `datasets/`

Per-dataset loader behind a thin protocol:

```python
# src/datasets/base.py  (imported as `from datasets.base import DatasetLoader`)
class DatasetLoader(Protocol):
    name: str
    version: str
    def iter_samples(self) -> Iterator[Sample]: ...
    def num_samples(self) -> int: ...
    def datasheet_path(self) -> Path: ...
```

- LoCoMo loader reads `data/locomo10.json` (or HF mirror) and yields validated `LoCoMoSample` pydantic objects.
- Other datasets can use the same protocol but back onto `datasets.load_dataset(...)` (HF).
- Data is **not** versioned in git (see §7). `scripts/download_data.py` downloads + checksums.

### 6.2 `baselines/`

```python
# src/baselines/base.py
class Baseline(Protocol):
    name: str          # e.g. "gpt-4-turbo", "pam@2.0"
    track: str         # "out_of_the_box" | "tuned"
    def setup(self, *, seed: int) -> None: ...
    def answer(self, prompt: str, *, max_tokens: int) -> BaselineResponse: ...
    def teardown(self) -> None: ...

@dataclass
class BaselineResponse:
    text: str
    usage: TokenUsage      # input_tokens, output_tokens, est_cost
    latency_ms: float
    raw: dict              # provider-specific
```

- M1 only ships `LiteLLMBaseline(model="gpt-4-turbo")`. The same class handles any LiteLLM-supported model in M2+.
- PAM, Honcho, Supermemory, mem0, Zep, Claude Code + Memory.md will each be a separate `baselines/<name>/` subpackage in later milestones.

### 6.3 `tasks/`

Each task is independent. A task knows how to take a `Sample` from its dataset, build prompts, drive a `Baseline`, and produce per-question `Prediction` records. It does **not** know how to score — scoring goes through `evals/`.

```python
# src/tasks/locomo/pipeline.py
def run_sample(
    sample: LoCoMoSample,
    baseline: Baseline,
    *,
    max_questions: int | None,
    progress: ProgressReporter,
) -> list[Prediction]: ...
```

LoCoMo specifics:
- Builds a "full conversation" prompt (no RAG in M1) following the LoCoMo paper format.
- Asks one question per call (matches current `gpt_utils.get_gpt_answers` behavior).
- Captures latency + token usage per call.

### 6.4 `evals/`

Unified across datasets and baselines:

- `qa_f1.py` — token-level F1 (LoCoMo paper's metric). Ported from the existing `evaluate_qa.py`.
- `llm_judge.py` — LiteLLM + `instructor` + pydantic rubric:
  ```python
  class JudgeVerdict(BaseModel):
      correct: bool
      score: float = Field(ge=0, le=1)
      reasoning: str
      confidence: float = Field(ge=0, le=1)
  ```
  Judge model is configurable (default `gpt-4o`). Prompt template lives in `evals/llm_judge.py` and is identical across tasks.
- `efficiency.py` — token counts (tiktoken for OpenAI, transformers tokenizer fallback), cost estimates per provider.
- `runtime.py` — wall-clock helpers for memory creation / retrieval phases (used by baselines that have those phases; LiteLLMBaseline has only "retrieval" = single call).
- `stats.py` — bootstrap CI + paired bootstrap test (used in M2+ multi-seed comparisons; defined now so the framework is ready).

### 6.5 `runner.py`

```python
@dataclass
class RunConfig:
    dataset: str          # "locomo"
    task: str             # "locomo"  (often == dataset; explicit so a dataset can have multiple tasks)
    baseline: str         # "gpt-4-turbo"
    baseline_kwargs: dict # {"temperature": 0.0, "max_tokens": 1024}
    exp_name: str
    seed: int = 42
    sample_index: int | None = None   # None = all
    max_questions: int | None = None
    output_dir: Path = Path("/outputs")
    mongo: bool = True
    dry_run: bool = False
    judge_model: str = "gpt-4o"

def run(cfg: RunConfig) -> RunResult: ...
```

`run()` is the single function exercised by both the CLI and any future programmatic caller. It:
1. Resolves dataset, task, baseline, evals from `registry.py`.
2. Seeds.
3. Iterates samples with rich progress.
4. Streams predictions to `output_dir/predictions.jsonl`.
5. Evaluates: F1 + LLM-judge + token/runtime efficiency.
6. Writes per-sample metric documents to MongoDB (one doc per sample, matching current `locomo_results` schema with extra fields).
7. Returns aggregate metrics.

### 6.6 `mongo.py`

- Connection params from env (`DB_NAME`, `CONNECTION_STRING`).
- Single `BenchmarkResult` pydantic schema; collection name derived from dataset (`{dataset}_results`) so existing dashboards keep working.
- Records `git_commit`, `image_digest`, `uv_lock_hash`, `seed`, `judge_model`, `baseline_kwargs` for provenance — required by `init_memory_bank.md` reproducibility section.

### 6.7 `reporting/`

- `query.py` pulls rows for an experiment.
- `html.py` renders the same HTML report the current `generate_report.py` produces (per-sample table, category breakdown, incorrect-response detail).
- `scripts/generate_report.py` is a thin typer CLI: `--experiment-name`, `--output-dir`.

## 7. Run model

### 7.1 Local

```bash
uv sync
uv run python scripts/run_benchmark.py \
  --dataset locomo \
  --baseline gpt-4-turbo \
  --exp-name locomo_gpt4_smoke \
  --seed 42 \
  --max-questions 5 \
  --sample-index 0 \
  --output-dir ./outputs/locomo_gpt4_smoke
```

### 7.2 Docker (local parity with Cloud Run image)

```bash
docker build -f cluster/Dockerfile -t pam-benchmark:dev .
docker run --rm \
  --env-file secrets.env \
  -v "$(pwd)/outputs:/outputs" \
  pam-benchmark:dev \
  scripts/run_benchmark.py \
  --dataset locomo --baseline gpt-4-turbo --exp-name locomo_gpt4_smoke --max-questions 5
```

### 7.3 Cloud Run Jobs

Same image; job invocation passes args:

```bash
gcloud run jobs deploy pam-benchmark \
  --image gcr.io/<project>/pam-benchmark:<digest> \
  --region <region> \
  --tasks 1 --max-retries 0 --task-timeout 86400 \
  --set-secrets OPENAI_API_KEY=openai-key:latest,...,CONNECTION_STRING=mongo-uri:latest \
  --command python --args scripts/run_benchmark.py,--dataset,locomo,--baseline,gpt-4-turbo,--exp-name,locomo_gpt4_full

gcloud run jobs execute pam-benchmark
```

Design notes:
- One Cloud Run Job execution = one `RunConfig`. Parallelism across samples is handled inside the job using `asyncio` + `aiolimiter` (the LiteLLM client is async); we do **not** rely on Cloud Run task fan-out for M1, to keep Mongo writes coherent.
- `PYTHONUNBUFFERED=1` so logs stream to Cloud Logging in real time.
- Outputs (`predictions.jsonl`) written to a Cloud Storage bucket if `--output-dir gs://...` is given (M2 polish; M1 supports local FS only — Mongo holds the metrics).

### 7.4 Dockerfile sketch (`cluster/Dockerfile`)

- Base: `python:3.12-slim`.
- Install `uv` via `pip install uv`.
- `COPY pyproject.toml uv.lock ./` then `uv sync --frozen --no-dev` (cache-friendly).
- `COPY src/ scripts/ ./`
- `ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app/src`
- `ENTRYPOINT ["python"]` so Cloud Run Jobs `--args` can pass `scripts/run_benchmark.py ...`.
- Build context is the project root (`docker build -f cluster/Dockerfile .`); `.dockerignore` stays at project root.

### 7.5 Script CLI surface

Every entrypoint in `scripts/` uses `typer`. `--exp-name` is the canonical name for the experiment identifier — same flag, same semantics across all scripts that touch experiment data.

| Script | Required | Common optional | Notes |
|---|---|---|---|
| `scripts/run_benchmark.py` | `--dataset`, `--baseline`, `--exp-name` | `--task` (defaults to `--dataset`), `--seed` (default 42), `--sample-index`, `--max-questions`, `--baseline-model`, `--baseline-kwargs` (JSON), `--judge-model` (default `gpt-4o`), `--output-dir` (default `./outputs/<exp-name>`), `--no-mongo`, `--dry-run`, `--log-format {rich,json}` | Single seed per invocation. To run ≥3 seeds, invoke 3× with different `--seed`; all share an `--exp-name`. |
| `scripts/generate_report.py` | `--exp-name` | `--output-dir` (default `./reports/<exp-name>`), `--format {html,md}` | Pulls Mongo rows for `--exp-name`, renders report. |
| `scripts/download_data.py` | `--dataset` | `--force` | Dataset-only; no `--exp-name` (data is experiment-agnostic). |

The `--exp-name` value is the primary key for grouping Mongo records, output artifacts, and reports. It MUST match exactly across `run_benchmark.py` invocations whose results belong to the same experiment.

## 8. Dependencies (`pyproject.toml`)

Managed by `uv`. Initial pins (M1 needs only the starred ones):

```
# Core *
python = ">=3.12,<3.13"          # 3.12 chosen for broadest wheel coverage across M2+ deps (torch, faiss-cpu, sentence-transformers)
litellm
pydantic >= 2
typer
rich
tenacity
aiolimiter
tiktoken
python-dotenv

# Data *
pandas
numpy
# NOTE: HF `datasets` is intentionally NOT a dep — its top-level import name collides
# with our `src/datasets/` package. M1 uses a custom JSON loader for LoCoMo. Revisit
# in M2 if we need HF Hub-hosted datasets (see §13 Q3).

# Judging *
instructor

# Storage *
pymongo

# Retrieval (M2+)
rank-bm25
sentence-transformers
faiss-cpu

# Stats (M2+ but defined now)
scipy

# Reporting *
jinja2

# Dev
pytest
pytest-asyncio
ruff
```

`uv.lock` is committed. Library upgrades go through a PR that bumps `uv.lock` deliberately.

**Python version note.** 3.12 is chosen for the broadest, most stable wheel coverage across the eventual stack — the binding constraints in M2+ are `torch` (used by `sentence-transformers`) and `faiss-cpu`. Re-evaluate whether to bump to 3.13 before M6 (retrieval baselines).

## 9. Evaluation methodology

Aligned with `docs/init_memory_bank.md` — `reproducibility/statistical-reporting.md` and `benchmark-spec/tasks-and-metrics.md`.

### 9.1 Mongo schema

One document per `(exp_name, sample_id, seed)` in `locomo_results`. Every question's full QA payload lives inside the document as a nested array — no separate per-question collection, no local prediction files. The existing report code in `src/tasks/locomo/generate_report.py` already reads a nested array; we extend its shape from "incorrect only" to "all questions".

```jsonc
{
  // identity
  "exp_name": "locomo_gpt4_full",
  "sample_id": "...",
  "sample_index": 0,
  "seed": 42,

  // system under test
  "baseline": "gpt-4-turbo",
  "baseline_kwargs": { "temperature": 0.0, "max_tokens": 1024 },
  "judge_model": "gpt-4o",
  "dataset_name": "locomo@1.0",
  "task_name": "locomo",

  // aggregate metrics (parity with current locomo_results + new fields)
  "total_questions": 200,
  "correct_count": 137,            // F1 ≥ 0.5
  "incorrect_count": 63,
  "overall_accuracy": 0.685,        // F1-based, kept for parity
  "judge_accuracy": 0.71,           // NEW: LLM-judge primary metric
  "category_single_hop_accuracy": ..., "category_single_hop_count": ...,
  "category_temporal_accuracy":  ..., "category_temporal_count":  ...,
  "category_open_domain_accuracy": ..., "category_open_domain_count": ...,
  "category_multi_hop_accuracy": ..., "category_multi_hop_count": ...,
  "category_adversarial_accuracy": ..., "category_adversarial_count": ...,
  "category_single_hop_llm_judge_accuracy": ..., "category_single_hop_llm_judge_total": ...,
  // ... per-category llm_judge_* mirrors ...
  "total_input_tokens": ...,
  "total_output_tokens": ...,
  "total_cost_usd": ...,
  "avg_latency_ms": ...,
  "p50_latency_ms": ...,
  "p95_latency_ms": ...,
  "execution_time_seconds": ...,

  // ALL QA records (replaces predictions.jsonl)
  "qa_responses": [
    {
      "question_num": 1,
      "question": "...",
      "expected_answer": "...",
      "model_answer": "...",            // key name matches existing report code
      "category": 1,
      "category_name": "single_hop",
      "f1_score": 0.83,
      "judge_correct": true,
      "judge_score": 0.95,
      "judge_confidence": 0.9,
      "judge_reasoning": "...",
      "input_tokens": 1234,
      "output_tokens": 56,
      "est_cost_usd": 0.012,
      "latency_ms": 1820
    }
    // ... one entry per question ...
  ],

  // provenance (per init_memory_bank.md reproducibility checklist)
  "git_commit": "...",
  "image_digest": "sha256:...",
  "uv_lock_hash": "...",
  "timestamp": "2026-05-23T12:34:56Z",
  "created_at": "2026-05-23T12:34:56.789Z"
}
```

Notes:
- `qa_responses` carries **every** question (correct + incorrect) so the report can show full per-question detail, not just errors. This replaces the existing `incorrect_responses` field; `generate_report.py` is updated to filter `qa_responses` where it previously read `incorrect_responses`.
- Document size: a LoCoMo sample has ~150–200 questions; with prompts/responses bounded at a few KB each, expected doc size is well under the Mongo 16 MB limit. If a future dataset breaches this, fall back to GridFS or a sibling collection.
- `model_answer` (not `prediction`) is the key name, matching the existing report code in `src/tasks/locomo/generate_report.py:892`.

### 9.2 Statistical reporting

Deferred to M2 when we run ≥3 seeds:
- Mean ± 95% bootstrap CI for every headline number.
- Paired bootstrap test for pairwise baseline comparisons.

## 10. Progress & logging

- `rich.progress.Progress` with per-sample bar and per-question subtask description.
- `rich.logging.RichHandler` for human-readable local logs.
- JSON structured logs (one line per event: `sample_started`, `question_answered`, `judge_called`, `sample_done`, `run_done`) gated on `--log-format json` for Cloud Run / Cloud Logging.
- Every long-running call (baseline answer, judge call) logs start + end + duration so a stuck run is diagnosable from logs alone.

## 11. Storage & reporting

- **MongoDB is the only persistent store.** Per-dataset collection (`locomo_results` for LoCoMo); one document per `(exp_name, sample_id, seed)`; all per-question payloads live in the document's `qa_responses` array (§9.1).
- **No local prediction files** — the previous plan for `outputs/<exp>/predictions.jsonl` is dropped. Mongo holds the same data, queryable.
- **No `run.log` persistence** — stdout/stderr is captured by Cloud Run Logs (remote) and the terminal (local). `rich` still renders progress live; we just don't write a separate log artifact.
- **Local artifacts kept** (small, useful for the immediate iteration):
  - `outputs/<exp-name>/<seed>/config.yaml` — resolved `RunConfig` snapshot.
  - `outputs/<exp-name>/<seed>/metrics.json` — copy of the aggregate fields written to Mongo, for quick local diff without a Mongo query.
- `scripts/generate_report.py --exp-name X` pulls all docs for that experiment from Mongo and writes HTML to `reports/<exp-name>/`. The report renders aggregates + per-question detail directly from `qa_responses`; no Mongo round-trip per question.

## 12. Milestone 1 — TODO checklist

> Each box is intended to become a PR-sized unit. Order is roughly sequential; some can parallelize after step 3.

### Repo & tooling
- [ ] **T1.1** Initialize `pyproject.toml` with `uv`, pin Python `>=3.12,<3.13`, add M1-starred deps, generate `uv.lock`.
- [ ] **T1.2** Create `.python-version`, `.dockerignore`.
- [ ] **T1.3** Add ruff config; add pre-commit (ruff format + ruff check).
- [ ] **T1.4** Update `.gitignore` for `outputs/`, `reports/`, `bench_venv/`, `venv/`, `.uv/`.

### Old code removal / migration
- [ ] **T2.1** Delete `src/tasks/locomo/environment/INIT.md`, `INTRO_TEMPLATE.md`, `init.py`, `pam_utils.py`, `pam_evaluate.py`, `pam_*.sh`, `run_pam_locomo.sh`. Git history preserves them for the M2 PAM port. `CLAUDE.md` already removed.
- [ ] **T2.2** Delete `src/tasks/locomo/{tests,solution}/`, `src/tasks/locomo/environment/{Dockerfile,docker-compose.yaml,requirements.txt}`.
- [ ] **T2.3** Delete `src/tasks/locomo/environment/task_eval/{claude_utils,gemini_utils,gpt_utils,hf_llm_utils,rag_utils,get_facts,get_session_summaries}.py`.
- [ ] **T2.4** Move `src/tasks/locomo/environment/prompt_examples/` up one level to `src/tasks/locomo/prompt_examples/`.
- [ ] **T2.5** Keep `src/tasks/locomo/instruction.md` in place (will be rewritten in T11.2).
- [ ] **T2.6** Delete `bench_venv/`, `venv/`, top-level `reports/` (regenerated by report script).

### New package skeleton
- [ ] **T3.1** Ensure `src/` contains subpackages: `datasets/`, `baselines/`, `tasks/`, `evals/`, `reporting/`, `utils/` (each with `__init__.py`). Rename existing empty `src/agents/` → `src/baselines/`. No top-level wrapper package, no `src/__init__.py`.
- [ ] **T3.2** Configure `pyproject.toml` as a uv-managed application (no build backend; `tool.uv.package = false` or equivalent). Local + Docker both set `PYTHONPATH=src`. Confirm `uv run python -c "import datasets, tasks, evals, baselines"` works.
- [ ] **T3.3** Create skeleton folders with placeholder README at `src/datasets/{longmemeval,memtrack}/` and `src/tasks/{longmemeval,memtrack}/` (slot visibility for future work).

### Datasets
- [ ] **T4.1** Define `datasets/base.py` `DatasetLoader` protocol + `Sample` dataclass.
- [ ] **T4.2** Keep `src/datasets/locomo/data/locomo10.json` in place (already gitignored). Loader reads from this path with a fallback to `scripts/download_data.py`.
- [ ] **T4.3** `datasets/locomo/schemas.py`: pydantic `LoCoMoSample`, `LoCoMoQA`, `LoCoMoConversationTurn`.
- [ ] **T4.4** `datasets/locomo/loader.py`: `LoCoMoLoader` that reads `locomo10.json` and yields validated samples.
- [ ] **T4.5** `scripts/download_data.py` with `--dataset locomo` (downloads + verifies sha256). For M1 may just check local file presence.
- [ ] **T4.6** `datasets/locomo/README.md` — dataset overview, license, citation.

### Baselines
- [ ] **T5.1** `baselines/base.py` `Baseline` protocol + `BaselineResponse`, `TokenUsage` dataclasses.
- [ ] **T5.2** `utils/llm.py`: async LiteLLM completion with `tenacity` retries (exponential backoff on 429/5xx) and `aiolimiter` rate limit (configurable RPM).
- [ ] **T5.3** `baselines/litellm_baseline.py`: `LiteLLMBaseline(model: str, **completion_kwargs)`. Uses `utils/llm.py`. Returns `BaselineResponse` with tokens + latency.
- [ ] **T5.4** Smoke test: hit gpt-4-turbo with a trivial prompt, assert response + tokens populated.

### Tasks (LoCoMo)
- [ ] **T6.1** `tasks/locomo/prompts.py`: port the conversation-formatting + question-asking prompts from old `gpt_utils.py`. Single function `build_prompt(sample, question)`.
- [ ] **T6.2** `tasks/locomo/pipeline.py`: `run_sample(sample, baseline, max_questions, progress) -> list[Prediction]`.
- [ ] **T6.3** Confirm prompt parity by running the same sample through old and new code; F1s should match within rounding.

### Evaluation
- [ ] **T7.1** `evals/base.py`: `Evaluator` protocol; `Prediction`, `EvalResult` dataclasses.
- [ ] **T7.2** `evals/qa_f1.py`: port `eval_question_answering` token-F1 logic from `task_eval/evaluation.py` and `evaluate_qa.py`. Drop the per-model file plumbing.
- [ ] **T7.3** `evals/llm_judge.py`: pydantic `JudgeVerdict`; prompt template; `instructor`-typed call via LiteLLM; retry on schema failure (≤2 retries).
- [ ] **T7.4** `evals/efficiency.py`: tiktoken-based token count helper + provider cost table (start with OpenAI; extensible).
- [ ] **T7.5** `evals/runtime.py`: timing context manager + helper to aggregate latency arrays into mean / p50 / p95.
- [ ] **T7.6** `evals/stats.py`: bootstrap CI fn (unused in M1 but the module exists so M2 doesn't need plumbing).
- [ ] **T7.7** Unit tests in `tests/test_qa_f1.py` and `tests/test_llm_judge_schema.py`.

### Runner & CLI
- [ ] **T8.1** `config.py`: pydantic `RunConfig`.
- [ ] **T8.2** `registry.py`: name → loader/task/baseline lookups; raises with helpful message on unknown name.
- [ ] **T8.3** `seeds.py`: `seed_all(seed)` (random, numpy; torch if/when added).
- [ ] **T8.4** `env.py`: load `secrets.env` locally; on Cloud Run rely on env injection.
- [ ] **T8.5** `progress.py`: rich Progress wrapper used by runner + tasks.
- [ ] **T8.6** `logging.py`: rich + JSON modes; configured by `--log-format`.
- [ ] **T8.7** `mongo.py`: pydantic `BenchmarkResult` + `QAResponse` schemas matching §9.1. One `write_sample_result(...)` call per `(exp_name, sample_id, seed)`; writes the full `qa_responses` array (all questions, correct + incorrect), all aggregates, and provenance fields. No separate per-question collection.
- [ ] **T8.8** `runner.py`: `run(cfg)` orchestrator.
- [ ] **T8.9** `cli.py`: typer app with the flag set defined in §7.5 (required: `--dataset`, `--baseline`, `--exp-name`; common: `--task`, `--seed`, `--sample-index`, `--max-questions`, `--baseline-model`, `--baseline-kwargs`, `--judge-model` default `gpt-4o`, `--output-dir`, `--no-mongo`, `--dry-run`, `--log-format`).
- [ ] **T8.10** `scripts/run_benchmark.py`: 3-line shim that adds `src/` to `sys.path` (if not already via `PYTHONPATH`) and runs `cli.app`.

### Reporting
- [ ] **T9.1** Refactor old `generate_report.py` (40 KB) into `src/reporting/query.py` + `src/reporting/html.py` + `src/reporting/templates/*.html.j2`. Identify pure functions, move to `src/reporting/`; the entry-point glue (typer CLI with `--exp-name`, `--output-dir`, `--format`) moves to `scripts/generate_report.py`. Update the code paths that previously read `incorrect_responses` (e.g. `src/tasks/locomo/generate_report.py:868`, `:892`) to read from the new `qa_responses` field — filter to incorrect entries where the old behavior expected incorrect-only.
- [ ] **T9.2** Verify the new report renders identically to the old one for a stored M0 experiment.

### Docker + Cloud Run
- [ ] **T10.1** `cluster/Dockerfile` as sketched in §7.4.
- [ ] **T10.2** `.dockerignore` at project root (exclude `venv/`, `bench_venv/`, `outputs/`, `reports/`, `.git/`, dataset JSON files).
- [ ] **T10.3** `cluster/deploy.sh` — wraps `docker build -f cluster/Dockerfile .`, `docker push`, `gcloud run jobs deploy` with secret bindings (OPENAI_API_KEY, CONNECTION_STRING, DB_NAME, etc.).
- [ ] **T10.4** `cluster/run_job.sh` — wraps `gcloud run jobs execute` and forwards `--exp-name`, `--dataset`, `--baseline`, etc. via `--args`.
- [ ] **T10.5** Local: `docker build -f cluster/Dockerfile -t pam-benchmark:dev .` + `docker run` smoke (single sample, 5 questions).
- [ ] **T10.6** Cloud Run: push image, deploy job, execute with `--max-questions 5 --sample-index 0`. Verify logs stream, Mongo write lands.
- [ ] **T10.7** Document deploy + execute commands in `README.md` (point at `cluster/deploy.sh` and `cluster/run_job.sh`).

### Documentation & memory bank
- [ ] **T11.1** Rewrite `README.md`: new quickstart (uv + Docker + Cloud Run), no Harbor references.
- [ ] **T11.2** Rewrite `src/tasks/locomo/instruction.md`: drop Harbor, drop PAM, document new CLI flags + outputs + Mongo schema.
- [ ] **T11.3** Initialize `.memory-bank/` per `docs/init_memory_bank.md`. Pre-fill from M1 reality:
  - `benchmark-overview/` — purpose, goals, scope as defined here.
  - `benchmark-spec/datasets-and-splits.md` — LoCoMo only for now; placeholders for others.
  - `benchmark-spec/tasks-and-metrics.md` — F1 + LLM-judge + token/runtime efficiency.
  - `benchmark-spec/evaluation-protocol.md` — single-call, no RAG, gpt-4-turbo configuration.
  - `baselines/system-cards.md` — gpt-4-turbo card (vendor, version, cost, ToS notes).
  - (no `baselines/results.md` — results live only in MongoDB + the rendered HTML report; the memory bank does not duplicate them.)
  - `reproducibility/compute-and-environment.md` — Docker image digest, uv.lock hash, `gcloud` job spec.
  - `reproducibility/reproducibility-checklist.md` — tick what M1 satisfies, flag what M2 owes.
  - `ethics-and-licensing/datasheet.md` — LoCoMo datasheet (paper-derived).
  - `ethics-and-licensing/licensing-and-data-handling.md` — LoCoMo license, OpenAI ToS check.
  - `distribution/hosting-and-versioning.md` — Mongo collection, image registry, data download path.
  - `tasks/active.md` — point to this plan.

### Acceptance
- [ ] **T12.1** Full M1 run: `gpt-4-turbo` on all 10 LoCoMo samples (no `--max-questions` cap), one seed, locally **and** on Cloud Run. Mongo populated. HTML report generated. Headline F1 within 1 pt of the legacy Harbor-based number on the same data file (sanity check).
- [ ] **T12.2** Tag the repo `m1` and capture the image digest in `baselines/system-cards.md`.

## 13. Resolved decisions

- **Folder layout.** No wrapper package; `src/` on `PYTHONPATH` with subdirs as top-level packages. Existing empty `src/agents/` is renamed to `src/baselines/`.
- **Legacy PAM files.** Deleted outright in T2.1; rely on git history for the M2 PAM port. No `legacy/` quarantine folder.
- **HF `datasets` shadow.** Custom loaders only — M1 ships a JSON loader for LoCoMo; HF `datasets` is not a dependency. Same approach for every future memory dataset that ships as JSON. Revisit only if a dataset is HF-Hub-only and not easily exportable.
- **Judge default model.** `gpt-4o` by default; overridable via `--judge-model` on `scripts/run_benchmark.py`.
- **LLM-judge vs. F1.** Report **both** wherever both are well-defined; LLM-judge is the **primary** metric for cross-baseline comparison. F1 stays for parity with the LoCoMo paper.
- **Seeds in M1.** Single seed per invocation, controlled by `--seed` (default 42). Running ≥3 seeds = invoking `run_benchmark.py` 3× with different `--seed` and the same `--exp-name`; aggregation at report time.
- **Mongo collection naming.** One collection per dataset; LoCoMo stays in `locomo_results`.
- **Async concurrency.** `aiolimiter` capped at 50 RPM for `gpt-4-turbo` to start; configurable in baseline kwargs.
- **No GCS, no `run.log`, no local `predictions.jsonl`.** Cloud Run Logs cover stdout/stderr; per-question payloads (questions, prompts, model answers, F1, judge verdicts, tokens, latency) live in Mongo as the `qa_responses` nested array on each `locomo_results` document (§9.1). Local `outputs/<exp-name>/<seed>/` keeps only `config.yaml` (resolved RunConfig) and `metrics.json` (mirror of aggregates), both small and useful for quick local diff.

No questions remain open. Ready to implement after sign-off.

## 14. Future milestones (preview, not committed)

- **M2** — PAM baseline ported off Harbor; ≥3 seeds; statistical significance; HTML report polish; cost/latency dashboard.
- **M3** — Add BEAM and DRBench datasets (per stated priority).
- **M4** — Add Honcho, Supermemory, mem0, Zep baselines (reuse their existing metrics where applicable; otherwise our `evals/`).
- **M5** — Claude Code + Memory.md, Claude Code + Obsidian, OpenClaw + .md baselines.
- **M6** — Retrieval baselines (rank-bm25, sentence-transformers + faiss) for tasks that support a retrieval setting.
- **M7** — LongMemEval, MEMTRACK, MemoryAgentBench datasets.
