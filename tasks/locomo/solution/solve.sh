#!/bin/bash
set -e

# Usage: 
#   - Via environment variables:
#     MODEL="gpt-4-turbo" BATCH_SIZE=20 solve.sh
#   - Default: runs gpt-4-turbo with batch-size 20
#
# Environment variables:
#   MODEL         - Model to evaluate (default: gpt-4-turbo)
#                   Supported: gpt-4-turbo, gpt-3.5-turbo, claude-sonnet, gemini-pro-1.0, pam
#   BATCH_SIZE    - Batch size for evaluation (default: 20)
#   USE_RAG       - Enable RAG mode (default: false)
#   OVERWRITE     - Overwrite existing predictions (default: false)
#   MAX_QUESTIONS - Maximum questions per sample, 0 = all (default: 0)
#   SAMPLE_INDEX  - Process only this sample index, -1 = all (default: -1)
#   PAM_DEBUG     - Skip memory creation, answer directly (default: false)
#
# PAM Agent:
#   When MODEL=pam, the PAM (Proactive AI Manager) agent is used:
#   - Processes conversations into structured memory
#   - Creates person profiles, session digests, topic files
#   - Answers questions based on organized memory structure
#   Example: MODEL=pam MAX_QUESTIONS=10 solve.sh

# Source secrets.env if available (for non-interactive Harbor runs)
if [ -f /workspace/secrets.env ]; then
  set -a
  source /workspace/secrets.env
  set +a
  echo "[INFO] Loaded secrets from /workspace/secrets.env"
fi

# Set defaults
MODEL="${MODEL:-gpt-4-turbo}"
USE_RAG="${USE_RAG:-false}"
OVERWRITE="${OVERWRITE:-false}"
MAX_QUESTIONS="${MAX_QUESTIONS:-0}"
SAMPLE_INDEX="${SAMPLE_INDEX:--1}"

# Set batch size based on model (PAM uses 10 for question batching to avoid rate limits, others use 20 for API calls)
if [ "$MODEL" = "pam" ]; then
  BATCH_SIZE="${BATCH_SIZE:-10}"
else
  BATCH_SIZE="${BATCH_SIZE:-20}"
fi

# Export BATCH_SIZE for PAM scripts
export BATCH_SIZE

# Show configuration
echo "========================================"
echo "LoCoMo Benchmark Evaluation"
echo "========================================"
echo "[INFO] MODEL='${MODEL}'"
echo "[INFO] BATCH_SIZE='${BATCH_SIZE}'"
echo "[INFO] USE_RAG='${USE_RAG}'"
echo "[INFO] OVERWRITE='${OVERWRITE}'"
echo "[INFO] MAX_QUESTIONS='${MAX_QUESTIONS}'"
echo "[INFO] SAMPLE_INDEX='${SAMPLE_INDEX}'"
echo "[INFO] EXPERIMENT_NAME='${EXPERIMENT_NAME:-}'"
echo ""

# Build command arguments
ARGS="--model ${MODEL} --batch-size ${BATCH_SIZE}"

if [ "$USE_RAG" = "true" ] || [ "$USE_RAG" = "1" ]; then
  ARGS="${ARGS} --use-rag"
  echo "[INFO] RAG mode enabled"
fi

if [ "$OVERWRITE" = "true" ] || [ "$OVERWRITE" = "1" ]; then
  ARGS="${ARGS} --overwrite"
  echo "[INFO] Overwrite mode enabled"
fi

if [ "$MAX_QUESTIONS" != "0" ] && [ -n "$MAX_QUESTIONS" ]; then
  ARGS="${ARGS} --max-questions ${MAX_QUESTIONS}"
  echo "[INFO] Limiting to ${MAX_QUESTIONS} questions per sample"
fi

if [ "$SAMPLE_INDEX" != "-1" ] && [ -n "$SAMPLE_INDEX" ]; then
  ARGS="${ARGS} --sample-index ${SAMPLE_INDEX}"
  echo "[INFO] Processing only sample index ${SAMPLE_INDEX}"
fi

echo ""
echo "Running: python /task_data/run_locomo.py ${ARGS}"
echo "========================================"
echo ""

# Run the evaluation
python /task_data/run_locomo.py ${ARGS}

echo ""
echo "========================================"
echo "LoCoMo evaluation completed!"
echo "========================================"
echo ""
echo "Results saved to:"
echo "  - /outputs/locomo10_qa.json (predictions)"
echo "  - /outputs/locomo10_qa_stats.json (statistics)"

# Show PAM-specific output if PAM was used
if [ "$MODEL" = "pam" ]; then
  echo ""
  echo "PAM Agent outputs:"
  echo "  - /task_logs/*/processing.log (memory creation log)"
  echo "  - /task_logs/*/pam_answers.json (PAM answers)"
  echo "  - /task_logs/*/questions/ (individual question logs)"
fi
