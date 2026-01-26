# LoCoMo Benchmark Task

This task evaluates the long-context memory capabilities of Large Language Models (LLMs) through question answering over extended conversation histories.

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
