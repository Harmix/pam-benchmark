#!/bin/bash
set -e

# Usage: 
#   - Via environment variables:
#     MODEL="gpt-4-turbo" BATCH_SIZE=20 solve.sh
#   - Default: runs gpt-4-turbo with batch-size 20
#
# Environment variables:
#   MODEL        - Model to evaluate (default: gpt-4-turbo)
#   BATCH_SIZE   - Batch size for evaluation (default: 20)
#   USE_RAG      - Enable RAG mode (default: false)
#   OVERWRITE    - Overwrite existing predictions (default: false)

# Source secrets.env if available (for non-interactive Harbor runs)
if [ -f /workspace/secrets.env ]; then
  set -a
  source /workspace/secrets.env
  set +a
  echo "[INFO] Loaded secrets from /workspace/secrets.env"
fi

# Set defaults
MODEL="${MODEL:-gpt-4-turbo}"
BATCH_SIZE="${BATCH_SIZE:-20}"
USE_RAG="${USE_RAG:-false}"
OVERWRITE="${OVERWRITE:-false}"

# Show configuration
echo "========================================"
echo "LoCoMo Benchmark Evaluation"
echo "========================================"
echo "[INFO] MODEL='${MODEL}'"
echo "[INFO] BATCH_SIZE='${BATCH_SIZE}'"
echo "[INFO] USE_RAG='${USE_RAG}'"
echo "[INFO] OVERWRITE='${OVERWRITE}'"
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
