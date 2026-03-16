#!/bin/bash
set -e

# Usage:
#   MODEL="gpt-4o" MAX_QUESTIONS=10 solve.sh
#
# Environment variables:
#   MODEL           - Model for answer generation (default: gpt-4o)
#   EVAL_MODEL      - Model for LLM-as-judge evaluation (default: gpt-4o)
#   MAX_QUESTIONS   - Maximum questions to process, 0 = all (default: 0)
#   QUESTION_ID     - Process a single question by ID (default: empty)
#   HISTORY_FORMAT  - History format: nl or json (default: nl)
#   COT             - Enable chain-of-thought (default: false)
#   OVERWRITE       - Overwrite existing predictions (default: false)
#   SKIP_EVAL       - Skip LLM-as-judge evaluation (default: false)

if [ -f /workspace/secrets.env ]; then
  set -a
  source /workspace/secrets.env
  set +a
  echo "[INFO] Loaded secrets from /workspace/secrets.env"
fi

MODEL="${MODEL:-gpt-4o}"
EVAL_MODEL="${EVAL_MODEL:-gpt-4o}"
MAX_QUESTIONS="${MAX_QUESTIONS:-0}"
HISTORY_FORMAT="${HISTORY_FORMAT:-nl}"
COT="${COT:-false}"
OVERWRITE="${OVERWRITE:-false}"
SKIP_EVAL="${SKIP_EVAL:-false}"

echo "========================================"
echo "LongMemEval Benchmark Evaluation"
echo "========================================"
echo "[INFO] MODEL='${MODEL}'"
echo "[INFO] EVAL_MODEL='${EVAL_MODEL}'"
echo "[INFO] MAX_QUESTIONS='${MAX_QUESTIONS}'"
echo "[INFO] QUESTION_ID='${QUESTION_ID:-}'"
echo "[INFO] HISTORY_FORMAT='${HISTORY_FORMAT}'"
echo "[INFO] COT='${COT}'"
echo "[INFO] OVERWRITE='${OVERWRITE}'"
echo "[INFO] SKIP_EVAL='${SKIP_EVAL}'"
echo "[INFO] EXPERIMENT_NAME='${EXPERIMENT_NAME:-}'"
echo ""

ARGS="--model ${MODEL} --eval-model ${EVAL_MODEL} --history-format ${HISTORY_FORMAT}"

if [ "$MAX_QUESTIONS" != "0" ] && [ -n "$MAX_QUESTIONS" ]; then
  ARGS="${ARGS} --max-questions ${MAX_QUESTIONS}"
  echo "[INFO] Limiting to ${MAX_QUESTIONS} questions"
fi

if [ -n "$QUESTION_ID" ]; then
  ARGS="${ARGS} --question-id ${QUESTION_ID}"
  echo "[INFO] Processing single question: ${QUESTION_ID}"
fi

if [ "$COT" = "true" ] || [ "$COT" = "1" ]; then
  ARGS="${ARGS} --cot"
  echo "[INFO] Chain-of-thought enabled"
fi

if [ "$OVERWRITE" = "true" ] || [ "$OVERWRITE" = "1" ]; then
  ARGS="${ARGS} --overwrite"
  echo "[INFO] Overwrite mode enabled"
fi

if [ "$SKIP_EVAL" = "true" ] || [ "$SKIP_EVAL" = "1" ]; then
  ARGS="${ARGS} --skip-eval"
  echo "[INFO] Skipping evaluation"
fi

echo ""
echo "Running: python /task_data/run_longmemeval.py ${ARGS}"
echo "========================================"
echo ""

python /task_data/run_longmemeval.py ${ARGS}

echo ""
echo "========================================"
echo "LongMemEval evaluation completed!"
echo "========================================"
echo ""
echo "Results saved to:"
echo "  - /outputs/longmemeval_predictions.jsonl (predictions)"
echo "  - /outputs/longmemeval_eval_results.jsonl (evaluation)"
echo "  - /outputs/longmemeval_stats.json (statistics)"
