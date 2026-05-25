# Pam Benchmark

The internal benchmark [Harmix](https://manager.harmix.ai) uses to validate **Pam**'s memory layer against competing memory products.

Pam (Proactive AI Manager) is Harmix's enterprise AI business assistant — it learns continuously from organizational data (documents, ERP/CRM systems, Linear, Slack, …) to anticipate problems, automate workflows, and resolve conflicts across disparate tools. The entire product hinges on accurate long-horizon recall of that data, so this benchmark answers one question repeatedly: **is Pam's memory at least as good as the best dedicated memory products on the tasks our customers care about?**

The methodology follows the standards in `docs/init_memory_bank.md` (datasheets, system cards, multi-seed statistics, reproducibility), so numbers stay defensible whether they're used internally for a release decision or externally in customer conversations.

## Status

**Milestone 1 — complete.** Harness validated end-to-end with `gpt-4-turbo` on the **LoCoMo** dataset; results in MongoDB, repo tagged `m1`.

**Milestone 2 — Pam baseline shipped.** `--baseline pam` runs Pam end-to-end on LoCoMo via the Pam API (one memory per conversation, batched SSE chat). Configuration via `--pam-batch-size` and `--pam-debug-user-id`. Competitors (Honcho, Supermemory, mem0, Zep, Claude Code variants, OpenClaw) follow in M4–M5. See `docs/m2_pam_baseline_plan.md` and `docs/benchmark_rewrite_plan.md` for the roadmap.

## Quick start (local)

Prerequisites: `uv >= 0.5`, Python 3.12, a populated `secrets.env` (see below), and the LoCoMo data file at `src/datasets/locomo/data/locomo10.json`.

```bash
# 1. Sync deps
uv sync

# 2. (One-time) Install git pre-commit hooks
uv run pre-commit install

# 3. Verify the dataset is in place
uv run python scripts/download_data.py --dataset locomo

# 4. Smoke run — 1 sample, 5 questions, gpt-4-turbo
uv run python scripts/run_benchmark.py \
  --dataset locomo \
  --baseline gpt-4-turbo \
  --exp-name local_smoke \
  --sample-index 0 \
  --max-questions 5

# 5. Render the HTML report (pulls from Mongo)
uv run python scripts/generate_report.py --exp-name local_smoke
open reports/local_smoke/report.html
```

The same scripts work without Mongo via `--no-mongo` (the report just won't have anything to pull).

## `secrets.env`

Required keys (loaded by `python-dotenv`):

```bash
OPENAI_API_KEY=sk-...
CONNECTION_STRING=mongodb+srv://...
DB_NAME=your-db
# Required when --baseline pam
PAM_API_HOST=...
PAM_API_USER=...
PAM_API_PASSWORD=...
```

`secrets.env` is gitignored. On Cloud Run Jobs these are injected via Secret Manager (see `cluster/deploy.sh`).

## Repo layout

```
.
├── cluster/                         # everything needed to run on a remote cluster
│   ├── Dockerfile                   # single image; runs locally + Cloud Run Jobs
│   ├── deploy.sh                    # build + push + gcloud run jobs deploy/update
│   └── run_job.sh                   # gcloud run jobs execute with --args forwarding
├── docs/
│   ├── init_memory_bank.md          # methodology standards (datasheet, model card, …)
│   ├── benchmark_rewrite_plan.md    # M1 scope + decisions + roadmap
│   └── m1_handoff.md                # how to run the M1 acceptance + tag
├── .memory-bank/                    # populated per init_memory_bank.md
├── scripts/                         # Python entrypoints; all accept --exp-name (except download)
│   ├── run_benchmark.py             # the only benchmark-run entrypoint
│   ├── generate_report.py           # pulls Mongo rows, renders HTML/MD
│   └── download_data.py             # idempotent dataset verifier/downloader
├── src/                             # PYTHONPATH=src; no wrapper package
│   ├── cli.py runner.py registry.py config.py seeds.py env.py mongo.py …
│   ├── datasets/<name>/             # one loader per dataset
│   ├── baselines/<name>/            # one system-under-test per baseline (Pam lands here in M2)
│   ├── tasks/<name>/                # one pipeline + prompts per dataset task
│   ├── evals/                       # shared metrics (F1, llm_judge, efficiency, runtime, stats)
│   ├── reporting/                   # Mongo → HTML/MD renderer
│   └── utils/                       # llm wrapper, io, timing
├── tests/                           # 100 unit tests across evals, runner, reporting, etc.
├── pyproject.toml uv.lock           # uv-managed dependencies
├── .python-version                  # 3.12
├── .pre-commit-config.yaml          # ruff + ruff-format + basic hygiene
├── .github/workflows/ci.yml         # lint + format + tests on PRs to main
├── .dockerignore .gitignore
└── secrets.env                      # gitignored
```

## Why this benchmark exists (the short version)

Pam has its own in-house memory layer; the other memory products in this benchmark (Honcho, Supermemory, mem0, Zep, Claude Code variants, OpenClaw) are competitors, not candidate backbones. The benchmark supports four recurring decisions:

1. **Competitive positioning.** Where does Pam's memory layer rank against each competitor, and on which workloads do we have an edge or a gap?
2. **Regression detection.** Does this Pam release recall organizational facts as accurately as the previous one?
3. **Configuration tuning.** Which model + retrieval config inside Pam performs best on enterprise data shapes (ERP records, Linear tickets, Slack threads, retrospectives)?
4. **Defensible external claims.** When we tell a Harmix prospect "Pam is N% better than competitor Y on workload Z," can we ship the experiment log to back it up?

Public memory benchmarks alone aren't enough because (a) several are saturating for top models, (b) they don't cover Harmix-shaped workloads (multi-tool coordination, long retrospectives), and (c) running competitors uniformly on the same data with the same scoring requires harness work that public datasets don't provide.

See `.memory-bank/benchmark-overview/README.md` for the longer version.

## CLI surface

| Script | Required | Useful optional |
|---|---|---|
| `scripts/run_benchmark.py` | `--dataset`, `--baseline`, `--exp-name` | `--seed` (default 42), `--sample-index`, `--max-questions`, `--baseline-model`, `--baseline-kwargs` (JSON), `--judge-model` (default `gpt-4o`), `--judge-concurrency`, `--output-dir`, `--no-mongo`, `--dry-run`, `--log-format {rich,json}`, `--pam-batch-size` (default 10), `--pam-debug-user-id` |
| `scripts/generate_report.py` | `--exp-name` | `--dataset` (default `locomo`), `--format {html,md}`, `--output-dir` |
| `scripts/download_data.py` | `--dataset` | `--force` |

The `--exp-name` value is the primary key for grouping Mongo records, output artifacts, and reports. For multi-seed runs invoke `run_benchmark.py` N times with the same `--exp-name` and different `--seed`.

## Outputs

Per-run local artifacts at `outputs/<exp-name>/<seed>/`:
- `config.yaml` — resolved `RunConfig`
- `metrics.json` — aggregate per-sample metrics (mirror of Mongo)

Per-sample Mongo document in `<dataset>_results` (e.g. `locomo_results`) — one document per `(exp_name, sample_id, seed)`, with the full per-question payload (question, expected, model answer, F1, judge verdict, tokens, latency) inside the `qa_responses` nested array. See `src/mongo.py` and `docs/benchmark_rewrite_plan.md` §9.1.

Reports at `reports/<exp-name>/report.html` are rendered on demand from Mongo by `scripts/generate_report.py`.

## Docker (local parity with Cloud Run)

```bash
docker build -f cluster/Dockerfile -t memory-benchmark:dev .

docker run --rm \
  --env-file secrets.env \
  -v "$(pwd)/outputs:/app/outputs" \
  memory-benchmark:dev \
    --dataset locomo --baseline gpt-4-turbo \
    --exp-name docker_smoke --sample-index 0 --max-questions 5
```

(The image's `ENTRYPOINT` is `python scripts/run_benchmark.py`, so flags go straight to the benchmark — no need to repeat the script name.)

## Cloud Run Jobs

One-time setup: enable Artifact Registry + Cloud Run, the `pam-rnd-cloud-run-jobs` repo in `harmix-pam-rnd` / `us-east1` exists, and the secrets are in Secret Manager (`openai-key`, `mongo-uri`, `mongo-db`).

```bash
# Build + push the image to the rnd registry (defaults to :latest)
./cluster/build_and_push.sh

# Execute the job (Cloud Run pulls :latest, runs ENTRYPOINT + --args)
./cluster/run_job.sh \
  --exp-name locomo_gpt4_full \
  --dataset locomo --baseline gpt-4-turbo

# Render the report from your laptop
uv run python scripts/generate_report.py --exp-name locomo_gpt4_full
```

The Cloud Run Job itself is created/managed via the GCP Console (or a separate deploy script) — `build_and_push.sh` only refreshes the image. Logs stream to Cloud Logging (use `--log-format json` for structured entries — `run_job.sh` adds this automatically).

## Tests & quality gates

```bash
env PYTHONPATH=src uv run pytest -q             # 100 unit tests
uv run ruff check src scripts tests             # lint
uv run ruff format src scripts tests            # format
uv run pre-commit run --all-files               # everything pre-commit will run
```

`.github/workflows/ci.yml` runs the same checks on every PR to `main`. Tests do not call any LLM — they cover shared logic (F1 scoring, judge rubric schema, runner aggregation, reporting, registry, prompt builder, dataset loader, RunConfig validation, baseline protocol).

## Adding a new dataset / baseline

- **Dataset:** create `src/datasets/<name>/{loader.py,schemas.py}` implementing `DatasetLoader`; register it in `src/registry.py`. Existing dataset code is untouched.
- **Baseline:** subclass `Baseline` from `src/baselines/base.py`; for plain LLMs reuse `LiteLLMBaseline`. Register in `src/registry.py`. Pam lands here in M2; competitors (Honcho, Supermemory, mem0, Zep, …) in M4.
- Add a system card to `.memory-bank/baselines/system-cards.md`.

See `src/baselines/README.md` and `src/tasks/locomo/instruction.md` for the patterns.

## License & data handling

- LoCoMo data is gitignored and bound by its upstream license — see `src/datasets/locomo/README.md`.
- Per-baseline vendor terms (e.g. published-comparison rules) are tracked in `.memory-bank/ethics-and-licensing/licensing-and-data-handling.md`.
- Customer-derived datasets (MEMTRACK once active) require PII redaction + access-control review before being added to this benchmark; Pam is SOC2/GDPR-aligned and the benchmark inherits those constraints.

## Links

- Harmix product: <https://manager.harmix.ai>
- Methodology standards: `docs/init_memory_bank.md`
- M1 plan & decisions: `docs/benchmark_rewrite_plan.md`
- M1 hand-off: `docs/m1_handoff.md`
