# Index.py - Unified Evaluation Pipeline

One script to rule them all! Automatically discovers configs, extracts Q/A pairs, and runs LLM judge evaluation.

## Quick Start

### Evaluate All Configs (Sequential)

```bash
python index.py
```

### Evaluate All Configs (Parallel - 3 workers per config)

```bash
python index.py --parallel 3
```

### Evaluate Specific Config

```bash
python index.py --config config_1_20251029_130807
```

### Summary Only (No Detailed Output)

```bash
python index.py --summary-only
```

## What It Does

1. **Auto-discovers** all configs in `./outputs/` directory
2. **Finds** corresponding YAML files in `./test_configs/`
3. **Extracts** questions and expected answers from YAML
4. **Reads** agent answers from log files
5. **Evaluates** using OpenAI Responses API with Pydantic
6. **Saves** results to `llm_judge_results.json` in each config folder
7. **Prints** detailed results and overall summary

### Save Raw OpenAI Responses

```bash
python index.py --save-raw
```

This saves the complete OpenAI API response for each question in a `judge-eval/` folder within each config directory.

### Combine Options

```bash
# Parallel evaluation with raw responses saved
python index.py --parallel 3 --save-raw

# Specific config with raw responses
python index.py --config config_1_20251029_130807 --save-raw --summary-only
```

## Command-line Options

```bash
python index.py [OPTIONS]
```

### Options

- `--output-dir PATH` - Output directory (default: `./outputs`)
- `--test-configs-dir PATH` - Test configs directory (default: `./test_configs`)
- `--config NAME` - Evaluate specific config only (default: all)
- `--model MODEL` - Override model from config files (e.g., `gpt-4o`)
- `--parallel N` - Number of parallel workers per config (default: 1)
- `--prompt-template PATH` - Custom prompt template file
- `--summary-only` - Show only summary, skip detailed results
- `--save-raw` - Save raw OpenAI responses to `judge-eval/` folder

## Example Workflows

### Development - Quick check on one config

```bash
python index.py --config config_1_20251029_130807 --summary-only
```

### Production - Evaluate all with speed

```bash
python index.py --parallel 5
```

### Custom Model - Use different model

```bash
python index.py --model gpt-4-turbo
```

### Custom Directories

```bash
python index.py \
  --output-dir ~/my-outputs \
  --test-configs-dir ~/my-configs
```

## Output Format

### Directory Structure with Raw Responses

When using `--save-raw`, each config directory will have:

```
outputs/
└── config_1_20251029_130807/
    ├── questions/
    │   ├── question_1.log
    │   ├── question_2.log
    │   └── question_3.log
    ├── judge-eval/                    ← Raw OpenAI responses
    │   ├── question_1_raw.json
    │   ├── question_2_raw.json
    │   └── question_3_raw.json
    └── llm_judge_results.json
```

### Raw Response Format

Each `question_N_raw.json` contains:

```json
{
  "config": "config_1_20251029_130807",
  "question_num": 1,
  "question": "What is the status of the oldest ticket?",
  "expected_answer": "done",
  "agent_answer": "Based on the ticket details...",
  "model": "gpt-4o",
  "system_prompt": "You are evaluating whether...",
  "response": {
    "id": "resp_123abc",
    "created_at": 1730217600,
    "model": "gpt-4o-2024-08-06",
    "status": "completed",
    "output_parsed": {
      "score": 1.0,
      "is_correct": true,
      "confidence": 0.95,
      "reasoning": "Agent correctly identified..."
    }
  }
}
```

This includes:
- Full question and answer context
- System prompt sent to OpenAI
- Complete API response metadata
- Parsed evaluation result

### Console Output

```
================================================================================
LLM-AS-JUDGE EVALUATION PIPELINE
================================================================================
Configs to evaluate: 3
Parallel workers: 1
================================================================================

================================================================================
Processing: config_1_20251029_130807
YAML: config_1.yaml
================================================================================
Questions: 3
Model: gpt-4o

  Question 1/3... ✓
  Question 2/3... ✓
  Question 3/3... ✗

✓ Results saved to: outputs/config_1_20251029_130807/llm_judge_results.json

================================================================================
CONFIG: config_1_20251029_130807
================================================================================

Question 1: ✓ CORRECT
  Q: What is the status of the oldest ticket that was once reassigned?
  Expected: done
  Score: 1.00
  Confidence: 0.95
  Reasoning: Agent correctly identified 'done' as the status

...

--------------------------------------------------------------------------------
Summary: 2/3 correct (66.7%), Avg Score: 0.67
```

### JSON Output (per config)

Each config gets a `llm_judge_results.json` file:

```json
{
  "config": "config_1_20251029_130807",
  "config_yaml": "config_1.yaml",
  "model": "gpt-4o",
  "summary": {
    "total_questions": 3,
    "correct_count": 2,
    "accuracy": 0.6666666666666666,
    "avg_score": 0.67,
    "avg_confidence": 0.88
  },
  "questions": [...],
  "expected_answers": [...],
  "results": {
    "1": {
      "score": 1.0,
      "is_correct": true,
      "confidence": 0.95,
      "reasoning": "...",
      "agent_answer": "..."
    },
    ...
  }
}
```

## Overall Summary

At the end, you get a summary across all configs:

```
================================================================================
OVERALL SUMMARY
================================================================================
config_1_20251029_130807: 2/3 (66.7%)
config_2_20251029_131141: 3/3 (100.0%)
config_3_20251029_131515: 1/1 (100.0%)

--------------------------------------------------------------------------------
TOTAL: 6/7 correct (85.7%)
================================================================================
```

## How It Works

### 1. Config Discovery

```
outputs/
├── config_1_20251029_130807/    ←─┐
├── config_2_20251029_131141/      │ Discovers these
└── config_3_20251029_131515/    ←─┘

test_configs/
├── config_1.yaml    ←─┐
├── config_2.yaml      │ Matches these
└── config_3.yaml    ←─┘
```

### 2. Q/A Extraction

For each config:
- Reads `benchmark.questions` from YAML
- Reads `benchmark.expected_answers` from YAML
- Reads agent answers from `questions/question_N.log` files

### 3. Evaluation

- Uses OpenAI Responses API with Pydantic models
- Structured output: score, is_correct, confidence, reasoning
- Parallel or sequential processing per config

### 4. Results

- Saves JSON results per config
- Prints detailed or summary output
- Overall statistics across all configs

## Requirements

```bash
pip install openai==2.6.1 pyyaml
```

## Environment

```bash
export OPENAI_API_KEY="your-key-here"
```
