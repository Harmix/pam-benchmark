# M1 Hand-off — How to Run the Acceptance Run

> **Status: complete.** T12.1 (acceptance run) and T12.2 (`m1` tag) both done. This document is preserved as a runbook for re-running the M1 harness in the future (e.g. as a regression check against a new `gpt-4-turbo` snapshot).

The implementation work for the M1 vertical slice (the harness that [Harmix](https://manager.harmix.ai) will use to compare Pam against memory competitors from M2 onward) is complete. The remaining items (T12.1, T12.2 in `benchmark_rewrite_plan.md`) cost real money and touch the Harmix GCP project, so they're left for you to run.

## What's done

- New architecture per `benchmark_rewrite_plan.md` (post-Harbor, library-first).
- `gpt-4-turbo` baseline via LiteLLM; `gpt-4o` LLM-judge with pydantic rubric; LoCoMo F1 ported.
- `scripts/run_benchmark.py` (runs the benchmark), `scripts/generate_report.py` (HTML/MD report from Mongo), `scripts/download_data.py` (data verify).
- `cluster/Dockerfile` + `cluster/deploy.sh` + `cluster/run_job.sh` for GCP Cloud Run Jobs.
- `.memory-bank/` initialized per `docs/init_memory_bank.md` (datasheet, system cards, reproducibility checklist, etc.).
- Tests pass; ruff clean.

## What's NOT done (your turn)

### T12.1 — Local smoke run (recommended first)

Cheap (~$0.05) — confirms the wiring works end-to-end against a real API and Mongo before you commit to the full run.

```bash
# Make sure secrets.env has OPENAI_API_KEY, CONNECTION_STRING, DB_NAME
uv run python scripts/run_benchmark.py \
  --dataset locomo \
  --baseline gpt-4-turbo \
  --exp-name m1_smoke \
  --sample-index 0 \
  --max-questions 3

uv run python scripts/generate_report.py --exp-name m1_smoke
open reports/m1_smoke/report.html
```

Expected: 3 questions answered, judged, written to `locomo_results` Mongo collection; HTML report renders.

### T12.1 — Full M1 acceptance run

Real money (~$20–40 depending on prompt length). Locally:

```bash
uv run python scripts/run_benchmark.py \
  --dataset locomo \
  --baseline gpt-4-turbo \
  --exp-name m1_locomo_gpt4_full
```

Or on Cloud Run Jobs (preferred — runs in the background, won't tie up your laptop):

```bash
export GCP_PROJECT=<your-project>
export GCP_REGION=europe-west1   # or whatever
export AR_REPO=pam-benchmark
export SECRETS=OPENAI_API_KEY=openai-key:latest,CONNECTION_STRING=mongo-uri:latest,DB_NAME=mongo-db:latest

# One-time: enable APIs and create the Artifact Registry repo
gcloud services enable run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com
gcloud artifacts repositories create pam-benchmark --repository-format=docker --location=$GCP_REGION

# One-time: put your secrets in Secret Manager (one per key)
echo -n "<your openai key>" | gcloud secrets create openai-key --data-file=-
echo -n "<your mongo uri>"  | gcloud secrets create mongo-uri  --data-file=-
echo -n "<your mongo db>"   | gcloud secrets create mongo-db   --data-file=-

# Build + push + deploy the job
./cluster/deploy.sh

# Execute the full run (blocks until done)
./cluster/run_job.sh --exp-name m1_locomo_gpt4_full --dataset locomo --baseline gpt-4-turbo
```

Then render the report from your laptop:

```bash
uv run python scripts/generate_report.py --exp-name m1_locomo_gpt4_full
open reports/m1_locomo_gpt4_full/report.html
```

### T12.2 — Tag the milestone

After the run succeeds and the headline F1 looks reasonable (sanity check: within ~1 pp of the legacy Harbor `gpt-4-turbo` number on LoCoMo):

1. Update `.memory-bank/baselines/system-cards.md` "Date of last evaluation" + image digest (printed by `cluster/deploy.sh`). Numbers themselves stay in Mongo + the rendered report — they aren't copied into the memory bank.
2. Tag: `git tag m1 && git push --tags`.

## Things I noticed that you may want to look at

- **F1 parity sanity check.** If the headline F1 is off by more than ~1 pp from the old Harbor number, compare a few specific QA records between old and new on the same sample/seed before concluding the port is wrong — most drift is from different gpt-4-turbo snapshots, not the prompt.
- **`reports/` at project root** still has old generated HTML from before the rewrite. The new layout writes to `reports/<exp-name>/`. Old files are now under `reports/` and are gitignored. Safe to `rm -rf reports/conversation_*.html reports/pam_*.html` if you want a clean slate.
- **Old `src/datasets/memtrack/data/`** still contains the legacy YAML test configs from the Harbor flow. They're gitignored and harmless; the new MEMTRACK loader (M2+) will decide whether to reuse them.
- **`pam-agent-credentials.json` at repo root** is gitignored and presumably from the old Pam flow; nothing in the new code reads it.
- **`bench_venv/` and `venv/` at repo root** — old virtualenvs. Now that uv manages `.venv/`, these can be `rm -rf`'d safely (your call; they're gitignored).

## CLI cheat sheet

```
scripts/run_benchmark.py    --dataset --baseline --exp-name [+ seed/sample/judge/...]
scripts/generate_report.py  --exp-name [--dataset locomo --format html|md]
scripts/download_data.py    --dataset
```

All scripts accept `--help`.

## If something breaks

- `uv sync --frozen` — re-create the venv from `uv.lock`.
- `env PYTHONPATH=src uv run pytest -q` — should be 16/16 passing.
- `env PYTHONPATH=src uv run ruff check src scripts tests` — should be clean.
- Logs: rich format locally, `--log-format json` on Cloud Run (already set by `run_job.sh`).
- Cloud Run Job logs: `gcloud run jobs executions list --region $GCP_REGION` then `gcloud run jobs executions logs read <execution>`.
