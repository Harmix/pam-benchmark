# PAM MemTrack Benchmark Task

This task evaluates an LLM agent's ability to process event history data (Linear tickets and Slack messages) and answer questions about it using the PAM (Proactive AI Manager) memory framework.

## Task Overview

MemTrack tests a memory agent's ability to:
1. Ingest raw event history data (Linear tickets and Slack messages) from JSON files
2. Organize the data according to the PAM Memory Agent Guide structure (daily digests, linear objects, slack threads)
3. Answer factual questions about the processed data — ticket statuses, assignees, message authors, timelines, etc.

Each benchmark **config** contains one event history file and a set of questions with expected answers.

## Running via Harbor

### Basic Usage (Claude Code agent)

```bash
TASK_CONFIGS=config_1 EXPERIMENT_NAME=memtrack_test harbor run \
  -d memtrack@1.0 \
  --registry-path datasets/memtrack/registry.json \
  --force-build
```

### Multiple Configs

```bash
TASK_CONFIGS="config_1,config_2,config_3" EXPERIMENT_NAME=memtrack_multi harbor run \
  -d memtrack@1.0 \
  --registry-path datasets/memtrack/registry.json \
  --force-build
```

### Environment Variables (Claude Code agent)

| Variable | Default | Description |
|----------|---------|-------------|
| `TASK_CONFIGS` | `config_1` | Comma-separated config names to run (e.g. `config_1,config_vg_15`) |
| `EXPERIMENT_NAME` | - | Name for the experiment run (used for MongoDB) |
| `DEBUG` | `false` | Enable stub mode (skips Claude Code, uses oracle output) |

---

## Running with PAM v2 Agent (`AGENT=pam_v2`)

When `AGENT=pam_v2`, the benchmark uses the PAM API endpoints directly instead
of running Claude Code. This mirrors the `MODEL=pam` mode in LongMemEval.

**Key difference from LongMemEval:** LongMemEval creates *one PAM memory per
question*. MemTrack creates *one PAM memory per config* (a single event history)
and answers *all questions in that config* against the same memory.

### Prerequisites

Set these in `secrets.env` at the project root or pass as environment variables:
- `PAM_API_HOST` — Base URL of the PAM API (e.g. `https://pam.example.com`)
- `PAM_API_USER` — Admin email for PAM login
- `PAM_API_PASSWORD` — Admin password for PAM login
- `OPENAI_API_KEY` — Required for LLM-as-judge evaluation (unless `SKIP_EVAL=true`)

### How It Works

For each config the runner executes the following pipeline:

```
0. POST {PAM_API_HOST}/v1/auth/login
   → Login with PAM_API_USER / PAM_API_PASSWORD to obtain an admin access token.
     Token is refreshed automatically on 401 responses throughout the run.

1. POST {PAM_API_HOST}/v1/admin/create-account
   → Create a dedicated PAM user (email: memtrack-{config_name}@benchmark.local)
     using the admin token from step 0.

2. POST {PAM_API_HOST}/v1/files/upload-generic/{user_id}
   → Upload event_history.json and linear_config.yaml (batched in groups of 5).
     Files are placed in the user's unsorted/generic_downloads/ folder.

3. POST {PAM_API_HOST}/v1/memory/pipeline/benchmark_memory/run?user_id={user_id}
   → Trigger the async memory pipeline, then poll /status every 30 s until the
     run reaches a terminal state (completed / failed / stopped / cancelled).

4. POST {PAM_API_HOST}/v1/messages/stream  (once per question)
   → Send each benchmark question via SSE chat and collect the answer.
     The final assistant text turn is used as the answer; injected_tokens is
     extracted from the "result" event payload.

5. POST {PAM_API_HOST}/v1/admin/backup-workspace/{user_id}
   → Backup the user's workspace to GCS before cleanup.

6. DELETE {PAM_API_HOST}/v1/admin/delete-account/{user_id}
   → Delete the user and all associated data.
```

Steps 1–3 are skipped when `DEBUG_USER_ID` is set (reuses an existing user/memory).
Steps 5–6 are skipped in `DEBUG=true` mode.

### Environment Variables (pam_v2)

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT` | - | Set to `pam_v2` to use PAM API endpoints |
| `PAM_API_HOST` | - | PAM API base URL (**required**) |
| `PAM_API_USER` | - | Admin email for PAM login (**required**) |
| `PAM_API_PASSWORD` | - | Admin password for PAM login (**required**) |
| `TASK_CONFIGS` | all configs | Comma-separated config names (e.g. `config_1,config_vg_15`) |
| `EVAL_MODEL` | `gpt-4o` | Model for LLM-as-judge evaluation |
| `MAX_QUESTIONS` | `0` | Max questions per config (0 = all) |
| `QUESTION_RANGE_START` | - | 1-based inclusive start question index per config |
| `QUESTION_RANGE_END` | - | 1-based inclusive end question index per config |
| `OVERWRITE` | `false` | Regenerate predictions even if a file already exists |
| `SKIP_EVAL` | `false` | Skip LLM-as-judge evaluation (generate only) |
| `DEBUG` | `false` | Skip backup and account deletion |
| `DEBUG_USER_ID` | - | Reuse an existing PAM user (skips account creation, upload, memory creation) |
| `EXPERIMENT_NAME` | - | MongoDB experiment identifier |

### Usage Examples

Full run on a single config:
```bash
AGENT=pam_v2 \
  PAM_API_HOST=https://pam.example.com \
  PAM_API_USER=admin@example.com \
  PAM_API_PASSWORD=secret \
  TASK_CONFIGS=config_1 \
  EXPERIMENT_NAME=memtrack_pam_v2_test \
  harbor run \
  -d memtrack@1.0 \
  --registry-path datasets/memtrack/registry.json \
  --force-build
```

Multiple configs:
```bash
AGENT=pam_v2 \
  PAM_API_HOST=https://pam.example.com \
  PAM_API_USER=admin@example.com \
  PAM_API_PASSWORD=secret \
  TASK_CONFIGS="config_1,config_2,config_3" \
  EXPERIMENT_NAME=memtrack_pam_v2_multi \
  harbor run \
  -d memtrack@1.0 \
  --registry-path datasets/memtrack/registry.json \
  --force-build
```

Quick test with 2 questions per config:
```bash
AGENT=pam_v2 \
  PAM_API_HOST=https://pam.example.com \
  PAM_API_USER=admin@example.com \
  PAM_API_PASSWORD=secret \
  TASK_CONFIGS=config_1 \
  MAX_QUESTIONS=2 \
  EXPERIMENT_NAME=memtrack_pam_v2_quick \
  harbor run \
  -d memtrack@1.0 \
  --registry-path datasets/memtrack/registry.json \
  --force-build
```

Generate predictions only (skip evaluation):
```bash
AGENT=pam_v2 \
  PAM_API_HOST=https://pam.example.com \
  PAM_API_USER=admin@example.com \
  PAM_API_PASSWORD=secret \
  TASK_CONFIGS=config_1 \
  SKIP_EVAL=true \
  EXPERIMENT_NAME=memtrack_pam_v2_gen \
  harbor run \
  -d memtrack@1.0 \
  --registry-path datasets/memtrack/registry.json \
  --force-build
```

Debug mode — skip backup/deletion for faster iteration:
```bash
AGENT=pam_v2 \
  PAM_API_HOST=https://pam.example.com \
  PAM_API_USER=admin@example.com \
  PAM_API_PASSWORD=secret \
  TASK_CONFIGS=config_1 \
  DEBUG=true \
  EXPERIMENT_NAME=memtrack_pam_v2_debug \
  harbor run \
  -d memtrack@1.0 \
  --registry-path datasets/memtrack/registry.json \
  --force-build
```

Reuse an existing user (skip account creation + memory pipeline):
```bash
AGENT=pam_v2 \
  PAM_API_HOST=https://pam.example.com \
  PAM_API_USER=admin@example.com \
  PAM_API_PASSWORD=secret \
  TASK_CONFIGS=config_1 \
  DEBUG=true \
  DEBUG_USER_ID=42 \
  EXPERIMENT_NAME=memtrack_pam_v2_reuse \
  harbor run \
  -d memtrack@1.0 \
  --registry-path datasets/memtrack/registry.json \
  --force-build
```

**Sharding by question index (parallel workers):** indices are 1-based and match
the order of questions in the config YAML. Example — worker A runs questions 1–5,
worker B runs 6–10:

```bash
# Worker A
AGENT=pam_v2 TASK_CONFIGS=config_1 \
  QUESTION_RANGE_START=1 QUESTION_RANGE_END=5 \
  EXPERIMENT_NAME=memtrack_pam_v2_wa harbor run ...

# Worker B
AGENT=pam_v2 TASK_CONFIGS=config_1 \
  QUESTION_RANGE_START=6 QUESTION_RANGE_END=10 \
  EXPERIMENT_NAME=memtrack_pam_v2_wb harbor run ...
```

> **Tip:** Put `PAM_API_HOST`, `PAM_API_USER`, and `PAM_API_PASSWORD` in
> `secrets.env` to avoid repeating them on every command.

### Performance Notes

- The memory pipeline (step 3) is the bottleneck — it can take several minutes
  per config depending on the size of the event history.
- All questions in a config share the same memory, so the pipeline cost is paid
  once per config (not per question), making pam_v2 more efficient than if each
  question had its own memory.
- Resume support: if `{config}_pam_v2_predictions.jsonl` already exists in
  `/task_logs`, it is reloaded and only evaluation is re-run (use `OVERWRITE=true`
  to force regeneration).

---

## Task Structure

```
tasks/memtrack/
├── environment/
│   ├── docker-compose.yaml        # Docker Compose configuration
│   ├── Dockerfile                 # Container build instructions
│   ├── requirements.txt           # Python dependencies
│   ├── setup_and_run.sh           # Claude Code agent runner (per config)
│   ├── run_memtrack_pam_v2.py     # PAM v2 benchmark runner (all configs)
│   ├── INIT.md                    # PAM Memory Agent Guide
│   ├── CLAUDE.md                  # PAM system context
│   ├── INTRO_TEMPLATE.md          # Company overview template
│   ├── init.py                    # PAM folder structure generator
│   └── parse_oracle_stub.py       # Oracle parser for DEBUG/stub mode
├── generate_report.py             # HTML report generator from MongoDB
├── instruction.md                 # This file
├── reports/                       # Generated HTML reports
├── solution/
│   └── solve.sh                   # Entry point script for Harbor
├── tests/
│   └── test_outputs.py            # Verification tests
└── task.toml                      # Task configuration
```

## Dataset

Configs are loaded from `datasets/memtrack/test_configs/*.yaml`. Each config contains:
- `benchmark.event_history` — relative path to the event history JSON
- `benchmark.questions` — list of questions to answer
- `benchmark.expected_answers` — list of expected answers (for evaluation)
- `linear` — Linear team/user configuration

Event histories are in `datasets/memtrack/test_event_histories/` and contain
chronological Linear ticket updates and Slack messages in JSON format.

## Evaluation

The task uses LLM-as-judge evaluation:
- Judge model: `EVAL_MODEL` (default `gpt-4o`)
- Per-question structured output: `score` (0–1), `is_correct`, `confidence`, `reasoning`
- Partial credit is awarded for partially correct answers

For the Claude Code agent, evaluation is run by `llm_judge_eval.py` immediately
after each config completes.

For the pam_v2 agent, evaluation is inline in `run_memtrack_pam_v2.py`.

## Output

### Claude Code agent

Per config, outputs are saved to `/task_logs/{config}_{timestamp}/`:
- `processing.log` — Claude's event history processing phase
- `questions/question_N.log` — Claude's answer for each question
- `llm_judge_results.json` — LLM judge evaluation results
- `execution_time.txt` — wall-clock execution time

### PAM v2 agent

Per config, outputs are saved to `/task_logs/`:
- `{config}_pam_v2_predictions.jsonl` — Raw PAM answers (one JSON line per question)
- `{config}_pam_v2_eval.jsonl` — Predictions with judge scores appended

## MongoDB Integration

Results are automatically saved to the `evaluation_results` collection when
`EXPERIMENT_NAME`, `DB_NAME`, and `CONNECTION_STRING` are set in `secrets.env`.

Each record contains:
- `config_name`, `dataset_name`, `agent_name`, `task_name`
- `total_questions`, `correct_count`, `accuracy`, `avg_score`, `avg_confidence`
- `execution_time_seconds`
- **PAM v2 only:** `total_memory_creation_duration_sec`, `avg_memory_creation_duration_sec`,
  `total_generation_duration_sec`, `avg_generation_duration_sec`,
  `total_injected_tokens`, `avg_injected_tokens`
- `incorrect_responses` — list of wrong answers with question, expected, agent answer, reasoning

## Generating Reports

After running an evaluation, generate an HTML report from MongoDB:

```bash
# From project root
python tasks/memtrack/generate_report.py --experiment-name my_experiment

# Or with environment variables
EXPERIMENT_NAME=my_experiment python tasks/memtrack/generate_report.py
```

Reports are saved to `tasks/memtrack/reports/` and include:
- Overall accuracy summary cards
- Results by config with timing columns (PAM v2 adds **Avg Memory Creation** and **Avg Injected Tokens**)
- Incorrect responses with judge reasoning

## API Keys

API keys are loaded from `secrets.env` at the project root:
- `OPENAI_API_KEY` — Required for LLM-as-judge evaluation
- `PAM_API_HOST` — PAM API base URL (required for pam_v2)
- `PAM_API_USER` — PAM admin email (required for pam_v2)
- `PAM_API_PASSWORD` — PAM admin password (required for pam_v2)
- `DB_NAME` — MongoDB database name (for saving results)
- `CONNECTION_STRING` — MongoDB connection string (for saving results)
