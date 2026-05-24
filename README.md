# PAM Benchmark

A library-first benchmark for comparing our memory solution (PAM) against competing memory products and simple LLM baselines on memory-oriented datasets.

The methodology follows the standards in `docs/init_memory_bank.md` (datasheets, system cards, multi-seed stats, reproducibility) so numbers stay defensible. The codebase is plain Python + `uv` + a single Dockerfile — no proprietary harness.

## Status

**Milestone 1 (active):** evaluate `gpt-4-turbo` on the **LoCoMo** dataset end-to-end. See `docs/benchmark_rewrite_plan.md` for scope, decisions, and the M2+ roadmap.

## Quick start (local)

Prerequisites: `uv >= 0.5`, Python 3.12, a populated `secrets.env` (see below), and the LoCoMo data file at `src/datasets/locomo/data/locomo10.json`.

```bash
# 1. Sync deps
uv sync

# 2. Verify the dataset is in place
uv run python scripts/download_data.py --dataset locomo

# 3. Smoke run — 1 sample, 5 questions, gpt-4-turbo
uv run python scripts/run_benchmark.py \
  --dataset locomo \
  --baseline gpt-4-turbo \
  --exp-name local_smoke \
  --sample-index 0 \
  --max-questions 5

# 4. Render the HTML report (pulls from Mongo)
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
│   └── benchmark_rewrite_plan.md    # M1 scope + open questions + roadmap
├── .memory-bank/                    # populated per init_memory_bank.md
├── scripts/                         # Python entrypoints; all accept --exp-name (except download)
│   ├── run_benchmark.py             # the only benchmark-run entrypoint
│   ├── generate_report.py           # pulls Mongo rows, renders HTML/MD
│   └── download_data.py             # idempotent dataset verifier/downloader
├── src/                             # PYTHONPATH=src; no wrapper package
│   ├── cli.py runner.py registry.py config.py seeds.py env.py mongo.py …
│   ├── datasets/<name>/             # one loader per dataset
│   ├── baselines/<name>/            # one system-under-test per baseline
│   ├── tasks/<name>/                # one pipeline + prompts per dataset task
│   ├── evals/                       # shared metrics (F1, llm_judge, efficiency, runtime, stats)
│   ├── reporting/                   # Mongo → HTML/MD renderer
│   └── utils/                       # llm wrapper, io, timing
├── tests/                           # unit tests for evals + judge schema
├── pyproject.toml uv.lock           # uv-managed dependencies
├── .python-version                  # 3.12
├── .dockerignore .gitignore
└── secrets.env                      # gitignored
```

## CLI surface

| Script | Required | Useful optional |
|---|---|---|
| `scripts/run_benchmark.py` | `--dataset`, `--baseline`, `--exp-name` | `--seed` (default 42), `--sample-index`, `--max-questions`, `--baseline-model`, `--baseline-kwargs` (JSON), `--judge-model` (default `gpt-4o`), `--judge-concurrency`, `--output-dir`, `--no-mongo`, `--dry-run`, `--log-format {rich,json}` |
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
docker build -f cluster/Dockerfile -t pam-benchmark:dev .

docker run --rm \
  --env-file secrets.env \
  -v "$(pwd)/outputs:/app/outputs" \
  pam-benchmark:dev \
  scripts/run_benchmark.py \
    --dataset locomo --baseline gpt-4-turbo \
    --exp-name docker_smoke --sample-index 0 --max-questions 5
```

## Cloud Run Jobs

One-time setup: enable Artifact Registry + Cloud Run, create a repo (e.g. `pam-benchmark`), and put the required secrets in Secret Manager (`openai-key`, `mongo-uri`, `mongo-db`).

```bash
export GCP_PROJECT=<your-project>
export GCP_REGION=europe-west1
export AR_REPO=pam-benchmark
export SECRETS=OPENAI_API_KEY=openai-key:latest,CONNECTION_STRING=mongo-uri:latest,DB_NAME=mongo-db:latest

# Build, push, and create/update the job
./cluster/deploy.sh

# Execute one run (uses --wait to block until completion)
./cluster/run_job.sh \
  --exp-name locomo_gpt4_full \
  --dataset locomo --baseline gpt-4-turbo

# Then render the report from your laptop
uv run python scripts/generate_report.py --exp-name locomo_gpt4_full
```

Logs stream to Cloud Logging (use `--log-format json` for structured entries — `run_job.sh` adds this automatically).

## Tests

```bash
env PYTHONPATH=src uv run pytest -q
```

Unit tests cover the F1 scoring math and judge-rubric schema validation. They do not call any LLM.

## Adding a new dataset / baseline

- **Dataset:** create `src/datasets/<name>/{loader.py,schemas.py}` implementing `DatasetLoader`; register it in `src/registry.py`. Existing dataset code is untouched.
- **Baseline:** subclass `Baseline` from `src/baselines/base.py`; for plain LLMs reuse `LiteLLMBaseline`. Register in `src/registry.py`.
- Add a system card to `.memory-bank/baselines/system-cards.md`.

See `src/baselines/README.md` and `src/tasks/locomo/instruction.md` for the patterns.

## License & data handling

LoCoMo data is gitignored and bound by its upstream license — see `src/datasets/locomo/README.md`. Per-baseline vendor terms (e.g. published comparison rules) are tracked in `.memory-bank/ethics-and-licensing/licensing-and-data-handling.md`.
