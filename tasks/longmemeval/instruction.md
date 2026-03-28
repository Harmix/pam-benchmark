# LongMemEval Benchmark Task

This task evaluates long-term conversational memory of LLMs using the LongMemEval benchmark — 500 questions across 6 categories, each requiring recall from ~48 conversation sessions (~115k tokens).

**Original Paper**: [LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory](https://arxiv.org/abs/2410.10813)

**GitHub**: https://github.com/xiaowu0162/LongMemEval

**Website**: https://xiaowu0162.github.io/long-mem-eval/

## Task Overview

LongMemEval tests an LLM's ability to:
1. Extract information from single conversation sessions (user facts, assistant facts, preferences)
2. Reason across multiple conversation sessions
3. Handle knowledge updates over time
4. Perform temporal reasoning about events

## Running via Harbor

### Basic Usage

```bash
EXPERIMENT_NAME=longmemeval_gpt4o harbor run \
  -d longmemeval@1.0 \
  --registry-path datasets/longmemeval/registry.json \
  --force-build
```

### With Custom Model

```bash
MODEL=gpt-4o-mini EXPERIMENT_NAME=longmemeval_mini harbor run \
  -d longmemeval@1.0 \
  --registry-path datasets/longmemeval/registry.json \
  --force-build
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL` | `gpt-4o` | Model for answer generation (`pam` for PAM Agent pipeline) |
| `EVAL_MODEL` | `gpt-4o` | Model for LLM-as-judge evaluation |
| `MAX_QUESTIONS` | `0` | Maximum questions to process (0 = all 500) |
| `QUESTION_ID` | - | Process a single question by ID (e.g., `e47becba`) |
| `QUESTION_RANGE_START` | - | 1-based inclusive start index in dataset JSON order (after `QUESTION_ID` filter, if any) |
| `QUESTION_RANGE_END` | - | 1-based inclusive end index in dataset JSON order (omit with `QUESTION_RANGE_START` only → through end of list) |
| `HISTORY_FORMAT` | `nl` | History format: `nl` or `json` (ignored when `MODEL=pam`) |
| `COT` | `false` | Enable chain-of-thought prompting (ignored when `MODEL=pam`) |
| `OVERWRITE` | `false` | Overwrite existing predictions |
| `SKIP_EVAL` | `false` | Skip LLM-as-judge evaluation (generate only) |
| `EXPERIMENT_NAME` | - | Name for the experiment run |
| `PAM_API_HOST` | - | PAM API base URL (required when `MODEL=pam`) |
| `PAM_API_USER` | - | Admin email for PAM login (required when `MODEL=pam`) |
| `PAM_API_PASSWORD` | - | Admin password for PAM login (required when `MODEL=pam`) |

### Examples

Full benchmark with GPT-4o (default):
```bash
EXPERIMENT_NAME=longmemeval_gpt4o harbor run \
  -d longmemeval@1.0 \
  --registry-path datasets/longmemeval/registry.json \
  --force-build
```

Quick test with 5 questions:
```bash
MODEL=gpt-4o MAX_QUESTIONS=5 EXPERIMENT_NAME=longmemeval_quick harbor run \
  -d longmemeval@1.0 \
  --registry-path datasets/longmemeval/registry.json \
  --force-build
```

Single question test:
```bash
QUESTION_ID=e47becba EXPERIMENT_NAME=longmemeval_single harbor run \
  -d longmemeval@1.0 \
  --registry-path datasets/longmemeval/registry.json \
  --force-build
```

With chain-of-thought:
```bash
MODEL=gpt-4o COT=true EXPERIMENT_NAME=longmemeval_cot harbor run \
  -d longmemeval@1.0 \
  --registry-path datasets/longmemeval/registry.json \
  --force-build
```

Generate predictions only (skip evaluation):
```bash
MODEL=gpt-4o SKIP_EVAL=true EXPERIMENT_NAME=longmemeval_gen harbor run \
  -d longmemeval@1.0 \
  --registry-path datasets/longmemeval/registry.json \
  --force-build
```

Run with a different eval model:
```bash
MODEL=gpt-4o EVAL_MODEL=gpt-4o-mini EXPERIMENT_NAME=longmemeval_eval_mini harbor run \
  -d longmemeval@1.0 \
  --registry-path datasets/longmemeval/registry.json \
  --force-build
```

**Sharding by index (parallel workers):** indices are **1-based** and match the order of questions in the dataset JSON (after `QUESTION_ID` filtering, if any). `MAX_QUESTIONS` is applied **after** the range slice. Example — worker A runs questions 1–10, worker B runs 11–20:

```bash
# Worker A
QUESTION_RANGE_START=1 QUESTION_RANGE_END=10 EXPERIMENT_NAME=longmemeval_w1 harbor run ...

# Worker B
QUESTION_RANGE_START=11 QUESTION_RANGE_END=20 EXPERIMENT_NAME=longmemeval_w2 harbor run ...
```

Use a distinct `EXPERIMENT_NAME` (or separate output volumes) per worker so MongoDB / artifacts do not collide; merge `longmemeval_predictions.jsonl` afterward if needed.

## Running with PAM Agent (`MODEL=pam`)

When `MODEL=pam`, the benchmark uses the PAM Agent API instead of direct OpenAI calls. Each of the 500 questions gets its own PAM user account with dedicated memory built from that question's conversation history.

### Prerequisites

- `PAM_API_HOST` — Base URL of the PAM API (e.g. `https://pam.example.com`)
- `PAM_API_USER` — Admin email for PAM login
- `PAM_API_PASSWORD` — Admin password for PAM login
- `OPENAI_API_KEY` — Still required for LLM-as-judge evaluation (unless `SKIP_EVAL=true`)

All should be set in `secrets.env` at the project root or passed as environment variables.

### How It Works

For each question the runner executes the following pipeline:

```
0. POST {PAM_API_HOST}/v1/auth/login
   → Login with PAM_API_USER / PAM_API_PASSWORD to get an admin access token

1. POST {PAM_API_HOST}/v1/admin/create-account
   → Create a dedicated PAM user (email: longmemeval-{question_id}@benchmark.local)
     using the admin token from step 0. JSON body includes `email`, `password`, `name`,
     `company_name`, and `position` (defaults: `Acme Inc`, `Engineer`, matching the API schema).

2. POST {PAM_API_HOST}/v1/files/upload-generic/{user_id}
   → Upload the question's ~48 haystack sessions as .txt files
     (batched in groups of 5 per request, stored in unsorted/generic_downloads/)

3. POST {PAM_API_HOST}/v1/memory/pipeline/benchmark_memory/run?user_id={user_id}
   → Trigger async memory pipeline, then poll status every 30s until completion
     (up to 1 hour). Pipeline stages: folder setup → sync → compress → deep analysis

4. POST {PAM_API_HOST}/v1/messages/stream
   → Send the question and collect the answer from the SSE stream

5. POST {PAM_API_HOST}/v1/admin/backup-workspace/{user_id}
   → Backup the user's workspace to GCS before cleanup

6. DELETE {PAM_API_HOST}/v1/admin/delete-account/{user_id}
   → Delete the user and all associated data
```

The login (step 0) is performed before each account creation to ensure a fresh admin token.

Each haystack session is serialized as a plain-text file named `{session_id}.txt` containing the session date and all conversation turns.

### Usage

Full benchmark with PAM:
```bash
MODEL=pam \
  PAM_API_HOST=https://pam.example.com \
  PAM_API_USER=admin@example.com \
  PAM_API_PASSWORD=secret \
  EXPERIMENT_NAME=longmemeval_pam \
  harbor run \
  -d longmemeval@1.0 \
  --registry-path datasets/longmemeval/registry.json \
  --force-build
```

Quick test with 3 questions:
```bash
MODEL=pam \
  PAM_API_HOST=https://pam.example.com \
  PAM_API_USER=admin@example.com \
  PAM_API_PASSWORD=secret \
  MAX_QUESTIONS=3 \
  EXPERIMENT_NAME=longmemeval_pam_quick \
  harbor run \
  -d longmemeval@1.0 \
  --registry-path datasets/longmemeval/registry.json \
  --force-build
```

Single question test:
```bash
MODEL=pam \
  PAM_API_HOST=https://pam.example.com \
  PAM_API_USER=admin@example.com \
  PAM_API_PASSWORD=secret \
  QUESTION_ID=e47becba \
  EXPERIMENT_NAME=longmemeval_pam_single \
  harbor run \
  -d longmemeval@1.0 \
  --registry-path datasets/longmemeval/registry.json \
  --force-build
```

Generate PAM predictions only (skip evaluation):
```bash
MODEL=pam \
  PAM_API_HOST=https://pam.example.com \
  PAM_API_USER=admin@example.com \
  PAM_API_PASSWORD=secret \
  SKIP_EVAL=true \
  EXPERIMENT_NAME=longmemeval_pam_gen \
  harbor run \
  -d longmemeval@1.0 \
  --registry-path datasets/longmemeval/registry.json \
  --force-build
```

> **Tip:** Put `PAM_API_HOST`, `PAM_API_USER`, and `PAM_API_PASSWORD` in `secrets.env` to avoid repeating them on every command.

### Performance Notes

- The PAM pipeline is significantly slower than direct LLM calls because each question requires account creation, file upload, full memory construction, and cleanup.
- Memory creation (`create-memory`) is the bottleneck — it can take several minutes per question depending on the number and size of files.
- The full 500-question benchmark with PAM may take many hours. Use `MAX_QUESTIONS` for initial testing.
- Resume support: existing predictions in `longmemeval_predictions.jsonl` are skipped automatically (use `OVERWRITE=true` to regenerate).

## Dataset

Uses `longmemeval_s_cleaned.json` (~277 MB, 500 questions):
- ~48 conversation sessions per question
- ~494 messages per question (~115k tokens)
- Each question's answer is buried within the conversation haystack

### Question Categories

| Category | Count | Description |
|----------|-------|-------------|
| Single-Session (User) | 70 | User-stated facts from one conversation |
| Single-Session (Assistant) | 56 | Assistant-stated facts from one conversation |
| Single-Session (Preference) | 30 | User preferences mentioned in passing |
| Multi-Session | 133 | Information scattered across many conversations |
| Temporal Reasoning | 133 | "When did X happen?" / ordering of events |
| Knowledge Update | 78 | Facts that changed over time |

## Task Structure

```
tasks/longmemeval/
├── environment/
│   ├── docker-compose.yaml        # Docker Compose configuration
│   ├── Dockerfile                 # Container build instructions
│   ├── requirements.txt           # Python dependencies
│   └── run_longmemeval.py         # Main benchmark runner
├── generate_report.py             # HTML report generator from MongoDB
├── instruction.md                 # This file
├── reports/                       # Generated HTML reports
├── solution/
│   └── solve.sh                   # Entry point script for Harbor
├── tests/
│   └── test.sh                    # Verification script
└── task.toml                      # Task configuration
```

## Evaluation

Uses LLM-as-judge evaluation (from the original LongMemEval paper):
- Different evaluation prompts per question type
- Temporal reasoning allows off-by-one errors
- Knowledge update accepts responses with both old and new info
- Preference questions check if user's personal info is utilized correctly
- Abstention questions (suffix `_abs`) check if model identifies unanswerable questions

## Output

The task produces:
- `/outputs/longmemeval_predictions.jsonl` — Model predictions (one per line)
- `/outputs/longmemeval_eval_results.jsonl` — Evaluation results with labels
- `/outputs/longmemeval_stats.json` — Aggregate statistics by question type

## MongoDB Integration

Results are automatically saved to MongoDB (one record per question category) when `EXPERIMENT_NAME`, `DB_NAME`, and `CONNECTION_STRING` are set in `secrets.env`.

Each record contains:
- `question_category` — Category name (e.g., `temporal-reasoning`)
- `total_questions`, `correct_count`, `incorrect_count`, `accuracy`
- `total_duration_sec`, `avg_duration_sec` — Timing per category
- `incorrect_answers` — List of wrong answers with `question`, `expected_answer`, `model_answer`, and `judge_explanation`

## Generating Reports

After running an evaluation, generate an HTML report from MongoDB:

```bash
# From project root
python tasks/longmemeval/generate_report.py --experiment-name my_experiment

# Or with environment variables
EXPERIMENT_NAME=my_experiment python tasks/longmemeval/generate_report.py
```

Reports are saved to `tasks/longmemeval/reports/` and include:
- Overall accuracy summary
- Accuracy breakdown by question category with timing
- Filterable list of incorrect responses with judge explanations

## API Keys

API keys are loaded from `secrets.env` at the project root:
- `OPENAI_API_KEY` — Required for GPT models (generation and evaluation)
- `DB_NAME` — MongoDB database name (for saving results)
- `CONNECTION_STRING` — MongoDB connection string (for saving results)
