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
| `MODEL` | `gpt-4o` | Model for answer generation |
| `EVAL_MODEL` | `gpt-4o` | Model for LLM-as-judge evaluation |
| `MAX_QUESTIONS` | `0` | Maximum questions to process (0 = all 500) |
| `QUESTION_ID` | - | Process a single question by ID (e.g., `e47becba`) |
| `HISTORY_FORMAT` | `nl` | History format: `nl` (natural language) or `json` |
| `COT` | `false` | Enable chain-of-thought prompting |
| `OVERWRITE` | `false` | Overwrite existing predictions |
| `SKIP_EVAL` | `false` | Skip LLM-as-judge evaluation (generate only) |
| `EXPERIMENT_NAME` | - | Name for the experiment run |

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
