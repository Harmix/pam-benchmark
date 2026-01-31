# LoCoMo Benchmark Task

This task evaluates the long-context memory capabilities of Large Language Models (LLMs) through question answering over extended conversation histories.

**Original Paper**: [Evaluating Very Long-Term Conversational Memory of LLM Agents](https://snap-research.github.io/locomo/) (ACL 2024)

**GitHub**: https://github.com/snap-research/locomo

**Project Page**: https://snap-research.github.io/locomo/

## Task Overview

The LoCoMo (Long Context Memory) benchmark tests an LLM's ability to:
1. Process and understand long multi-session conversations between two people
2. Answer questions that require recalling specific facts from the conversation
3. Handle temporal reasoning across conversation sessions
4. Perform multi-hop reasoning over conversation content

## Running via Harbor

### Basic Usage

```bash
EXPERIMENT_NAME=my_experiment harbor run \
  -d locomo@1.0 \
  --registry-path datasets/locomo/registry.json \
  --force-build
```

### With Custom Model

```bash
MODEL=claude-sonnet EXPERIMENT_NAME=my_experiment harbor run \
  -d locomo@1.0 \
  --registry-path datasets/locomo/registry.json \
  --force-build
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL` | `gpt-4-turbo` | Model to evaluate (gpt-4-turbo, gpt-3.5-turbo, claude-sonnet, gemini-pro-1.0) |
| `BATCH_SIZE` | `20` | Number of questions per batch |
| `USE_RAG` | `false` | Enable RAG-based evaluation |
| `OVERWRITE` | `false` | Overwrite existing predictions |
| `MAX_QUESTIONS` | `0` | Maximum questions per sample (0 = all questions) |
| `EXPERIMENT_NAME` | - | Name for the experiment run |

### Examples

Evaluate GPT-4 Turbo (default):
```bash
EXPERIMENT_NAME=locomo_gpt4 harbor run \
  -d locomo@1.0 \
  --registry-path datasets/locomo/registry.json \
  --force-build
```

Evaluate Claude Sonnet:
```bash
MODEL=claude-sonnet EXPERIMENT_NAME=locomo_claude harbor run \
  -d locomo@1.0 \
  --registry-path datasets/locomo/registry.json \
  --force-build
```

Evaluate with smaller batch size:
```bash
MODEL=gpt-4-turbo BATCH_SIZE=10 EXPERIMENT_NAME=locomo_small_batch harbor run \
  -d locomo@1.0 \
  --registry-path datasets/locomo/registry.json \
  --force-build
```

Run on a subset of questions (e.g., first 10 questions per sample):
```bash
MAX_QUESTIONS=10 EXPERIMENT_NAME=locomo_subset harbor run \
  -d locomo@1.0 \
  --registry-path datasets/locomo/registry.json \
  --force-build
```

Quick test run (5 questions, small batch):
```bash
MODEL=gpt-4-turbo MAX_QUESTIONS=5 BATCH_SIZE=5 EXPERIMENT_NAME=locomo_quick_test harbor run \
  -d locomo@1.0 \
  --registry-path datasets/locomo/registry.json \
  --force-build
```

## Dataset Structure

The benchmark uses the `locomo10.json` dataset containing:
- **Conversations**: Multi-session dialogues with dates and speaker information
- **QA Pairs**: Questions with ground truth answers and evidence references

### Question Categories

- **Category 1**: Single-hop factual questions (multi-answer with partial F1 scoring)
- **Category 2**: Temporal reasoning questions (date/time related)
- **Category 3**: Open-domain questions
- **Category 4**: Multi-hop reasoning questions
- **Category 5**: Adversarial questions (testing for hallucination)

## Task Structure

```
tasks/locomo/
├── environment/
│   ├── docker-compose.yaml    # Docker Compose configuration
│   ├── Dockerfile             # Container build instructions
│   ├── global_methods.py      # LLM API utility functions
│   ├── prompt_examples/       # Prompt templates and examples
│   ├── requirements.txt       # Python dependencies
│   ├── run_locomo.py          # Main evaluation script
│   └── task_eval/             # Evaluation modules
├── instruction.md             # This file
├── solution/
│   └── solve.sh               # Entry point script for Harbor
└── task.toml                  # Task configuration
```

## Supported Models

- **OpenAI**: gpt-4-turbo, gpt-3.5-turbo, gpt-3.5-turbo-16k
- **Anthropic**: claude-sonnet, claude-haiku
- **Google**: gemini-pro-1.0

## Output

The task produces:
- `/outputs/locomo10_qa.json`: Predictions with F1 scores for each QA pair
- `/outputs/locomo10_qa_stats.json`: Aggregate statistics by question category

## Evaluation Metrics

- **F1 Score**: Token-level F1 between predicted and ground truth answers
- **Category Accuracy**: Aggregate accuracy for each question category
- **Overall Accuracy**: Weighted average across all categories

## API Keys

API keys are loaded from `secrets.env` at the project root. Required keys depend on the model:
- `OPENAI_API_KEY` - for GPT models
- `ANTHROPIC_API_KEY` - for Claude models
- `GOOGLE_API_KEY` - for Gemini models

## MongoDB Integration

Results are automatically saved to MongoDB when the following environment variables are configured in `secrets.env`:
- `DB_NAME` - MongoDB database name
- `CONNECTION_STRING` - MongoDB connection string

The results are saved to the `locomo_results` collection with the following fields:
- `experiment_name` - Name of the experiment
- `model` - Model used for evaluation
- `dataset_name` - Dataset identifier (locomo@1.0)
- `task_name` - Task identifier (locomo)
- `total_questions` - Total number of questions evaluated
- `correct_count` - Number of correct answers (F1 >= 0.5)
- `incorrect_count` - Number of incorrect answers
- `overall_accuracy` - Overall F1 accuracy
- `category_X_accuracy` - Accuracy for each question category
- `category_X_count` - Number of questions per category
- `execution_time_seconds` - Total execution time
- `batch_size`, `use_rag`, `max_questions` - Configuration settings
- `incorrect_responses` - List of incorrect answers with questions, expected answers, and model answers
- `timestamp`, `created_at` - Timestamps

## Generating Reports

After running evaluations, you can generate an HTML report from MongoDB results:

```bash
# From project root
python tasks/locomo/generate_report.py --experiment-name my_experiment

# Or with environment variables
EXPERIMENT_NAME=my_experiment python tasks/locomo/generate_report.py
```

The report includes:
- Overall accuracy summary
- Accuracy breakdown by question category (Single-hop, Temporal, Open-domain, Multi-hop, Adversarial)
- Detailed list of incorrect responses with questions, expected answers, and model answers
- Execution time statistics

Reports are saved to `tasks/locomo/reports/`
