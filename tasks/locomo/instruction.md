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
| `SAMPLE_INDEX` | `0` | Sample index to process (PAM only, for testing single samples) |
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
│   ├── task_eval/             # Evaluation modules
│   │
│   │   # PAM Agent files
│   ├── INIT.md                # PAM Memory Agent Guide
│   ├── init.py                # PAM structure generator
│   ├── INTRO_TEMPLATE.md      # Company template
│   ├── CLAUDE.md              # PAM system context
│   ├── pam_utils.py           # PAM utility functions
│   ├── pam_setup.sh           # PAM setup phase
│   ├── pam_process.sh         # PAM processing phase
│   ├── pam_answer.sh          # PAM answering phase
│   └── run_pam_locomo.sh      # PAM main orchestrator
├── instruction.md             # This file
├── solution/
│   └── solve.sh               # Entry point script for Harbor
├── generate_report.py         # HTML report generator
├── reports/                   # Generated reports directory
└── task.toml                  # Task configuration
```

## Supported Models

- **OpenAI**: gpt-4-turbo, gpt-3.5-turbo, gpt-3.5-turbo-16k
- **Anthropic**: claude-sonnet, claude-haiku
- **Google**: gemini-pro-1.0
- **PAM Agent**: pam (Proactive AI Manager with memory structure)

### PAM Agent

PAM (Proactive AI Manager) is a memory-augmented agent that:
1. **Processes conversations** into a structured memory format (person profiles, session digests, topic files)
2. **Creates a knowledge base** from conversation history
3. **Answers questions** by referencing the organized memory structure

To run with PAM:
```bash
MODEL=pam MAX_QUESTIONS=10 EXPERIMENT_NAME=locomo_pam harbor run \
  -d locomo@1.0 \
  --registry-path datasets/locomo/registry.json \
  --force-build
```

PAM uses Claude Code internally and creates the following memory structure:
- `02_people/` - Person profiles for each speaker
- `09_activity_streams/daily_digests/` - Session-by-session conversation summaries
- `09_activity_streams/linear_objects/` - Topic/event files
- `processed_data.md` - Overall conversation summary

### PAM Debug Mode

Debug mode skips the memory creation phase (which takes ~15 minutes) and answers questions directly from raw conversation data. Useful for testing answer extraction and evaluation logic.

```bash
# Debug mode - skip memory creation, answer from raw conversation
EXPERIMENT_NAME=locomo_pam_debug MODEL=pam SAMPLE_INDEX=0 PAM_DEBUG=true MAX_QUESTIONS=10 harbor run \
  -d locomo@1.0 \
  --registry-path datasets/locomo/registry.json \
  --force-build
```

**What debug mode does:**
- Skips Phase 1 (Setup) - No PAM folder structure creation
- Skips Phase 2 (Processing) - No memory organization by Claude
- Creates minimal context - Extracts raw conversation to `/workspace/processed_data.md`
- Runs Phase 3 (Answering) - Claude answers questions based on raw conversation
- Runs Phase 4 (Evaluation) - Metrics are still calculated and saved to MongoDB

**When to use debug mode:**
- Testing answer extraction and parsing logic
- Testing evaluation/F1 calculation
- Testing MongoDB saving
- Quick iteration without waiting for memory creation

### Parallel Execution for PAM

Since PAM takes ~960 seconds per sample, you can run multiple samples in parallel using separate terminal sessions.

**Recommended approach - Multiple Terminal Sessions:**

```bash
# Terminal 1: Build image with first sample (use --force-build)
EXPERIMENT_NAME=locomo_pam MODEL=pam SAMPLE_INDEX=0 harbor run \
  -d locomo@1.0 \
  --registry-path datasets/locomo/registry.json \
  --force-build

# Terminal 2: Run sample 1 (no --force-build, reuses built image)
EXPERIMENT_NAME=locomo_pam MODEL=pam SAMPLE_INDEX=1 harbor run \
  -d locomo@1.0 \
  --registry-path datasets/locomo/registry.json

# Terminal 3: Run sample 2
EXPERIMENT_NAME=locomo_pam MODEL=pam SAMPLE_INDEX=2 harbor run \
  -d locomo@1.0 \
  --registry-path datasets/locomo/registry.json

# ... continue for samples 3-9 in additional terminals
```

**Quick test with limited questions:**

```bash
# Terminal 1 (with --force-build)
EXPERIMENT_NAME=locomo_pam_test MODEL=pam SAMPLE_INDEX=0 MAX_QUESTIONS=5 harbor run \
  -d locomo@1.0 \
  --registry-path datasets/locomo/registry.json \
  --force-build

# Terminal 2 (without --force-build)
EXPERIMENT_NAME=locomo_pam_test MODEL=pam SAMPLE_INDEX=1 MAX_QUESTIONS=5 harbor run \
  -d locomo@1.0 \
  --registry-path datasets/locomo/registry.json
```

**Important notes:**
- Use `--force-build` only on the **first** terminal to build the Docker image
- Subsequent terminals should **omit** `--force-build` to reuse the existing image
- Start Terminal 2+ after Terminal 1 has finished building (you'll see evaluation starting)
- All samples share the **same EXPERIMENT_NAME** in MongoDB for easy querying
- Each sample's results are saved to MongoDB with `sample_id` and `sample_index` fields

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
- `ANTHROPIC_API_KEY` - for Claude models (not needed for PAM, only used for direct Claude API models (claude-sonnet, claude-haiku))
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
