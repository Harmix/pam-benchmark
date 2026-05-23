#!/bin/bash
set -e

# Usage:
#   Claude Code agent (default):
#     TASK_CONFIGS="config_1,config_2" solve.sh
#     DEBUG=true TASK_CONFIGS=config_1 solve.sh   # stub mode
#
#   PAM v2 agent (PAM API endpoints):
#     AGENT=pam_v2 TASK_CONFIGS=config_1 solve.sh
#     AGENT=pam_v2 TASK_CONFIGS="config_1,config_2" EVAL_MODEL=gpt-4o solve.sh

# Source secrets.env if available (for non-interactive Harbor runs)
if [ -f /workspace/secrets.env ]; then
  set -a
  source /workspace/secrets.env
  set +a
fi

# Shared defaults
AGENT="${AGENT:-}"
DEBUG="${DEBUG:-false}"
EVAL_MODEL="${EVAL_MODEL:-gpt-4o}"
MAX_QUESTIONS="${MAX_QUESTIONS:-0}"
OVERWRITE="${OVERWRITE:-false}"
SKIP_EVAL="${SKIP_EVAL:-false}"

echo "========================================"
echo "PAM Task Execution"
echo "========================================"
echo "[INFO] AGENT='${AGENT}'"
echo "[INFO] TASK_CONFIGS='${TASK_CONFIGS:-}'"
echo "[INFO] EXPERIMENT_NAME='${EXPERIMENT_NAME:-}'"
echo "[INFO] DEBUG='${DEBUG}'"
echo "[INFO] Command line args: $@"
echo ""

# ============================================================
# Branch: PAM v2 Agent
# ============================================================
if [ "${AGENT}" = "pam_v2" ]; then

  echo "========================================"
  echo "Running pam_v2 Agent (PAM API endpoints)"
  echo "========================================"
  echo "[INFO] EVAL_MODEL='${EVAL_MODEL}'"
  echo "[INFO] PAM_API_HOST='${PAM_API_HOST:-}'"
  echo "[INFO] PAM_API_USER='${PAM_API_USER:-}'"
  echo "[INFO] MAX_QUESTIONS='${MAX_QUESTIONS}'"
  echo "[INFO] SKIP_EVAL='${SKIP_EVAL}'"
  echo "[INFO] OVERWRITE='${OVERWRITE}'"
  echo "[INFO] QUESTION_RANGE_START='${QUESTION_RANGE_START:-}'"
  echo "[INFO] QUESTION_RANGE_END='${QUESTION_RANGE_END:-}'"
  echo "[INFO] DEBUG_USER_ID='${DEBUG_USER_ID:-}'"
  echo ""

  # Validate required PAM credentials
  MISSING=""
  [ -z "${PAM_API_HOST:-}" ]     && MISSING="${MISSING} PAM_API_HOST"
  [ -z "${PAM_API_USER:-}" ]     && MISSING="${MISSING} PAM_API_USER"
  [ -z "${PAM_API_PASSWORD:-}" ] && MISSING="${MISSING} PAM_API_PASSWORD"
  if [ -n "${MISSING}" ]; then
    echo "[ERROR] Missing required env vars for AGENT=pam_v2:${MISSING}"
    exit 1
  fi

  mkdir -p /task_logs

  ARGS="--configs-dir /task_data/test_configs"
  ARGS="${ARGS} --task-data-dir /task_data"
  ARGS="${ARGS} --out-dir /task_logs"
  ARGS="${ARGS} --eval-model ${EVAL_MODEL}"

  # TASK_CONFIGS is consumed directly from the environment by run_memtrack_pam_v2.py
  if [ -n "${TASK_CONFIGS:-}" ]; then
    echo "[INFO] Will process TASK_CONFIGS='${TASK_CONFIGS}'"
  fi

  if [ "${MAX_QUESTIONS}" != "0" ] && [ -n "${MAX_QUESTIONS}" ]; then
    ARGS="${ARGS} --max-questions ${MAX_QUESTIONS}"
    echo "[INFO] Limiting to ${MAX_QUESTIONS} questions per config"
  fi

  if [ -n "${QUESTION_RANGE_START:-}" ]; then
    ARGS="${ARGS} --question-range-start ${QUESTION_RANGE_START}"
    echo "[INFO] Question range start (1-based): ${QUESTION_RANGE_START}"
  fi
  if [ -n "${QUESTION_RANGE_END:-}" ]; then
    ARGS="${ARGS} --question-range-end ${QUESTION_RANGE_END}"
    echo "[INFO] Question range end (1-based): ${QUESTION_RANGE_END}"
  fi

  if [ "${OVERWRITE}" = "true" ] || [ "${OVERWRITE}" = "1" ]; then
    ARGS="${ARGS} --overwrite"
    echo "[INFO] Overwrite mode enabled"
  fi

  if [ "${SKIP_EVAL}" = "true" ] || [ "${SKIP_EVAL}" = "1" ]; then
    ARGS="${ARGS} --skip-eval"
    echo "[INFO] Skipping evaluation"
  fi

  if [ "${DEBUG}" = "true" ] || [ "${DEBUG}" = "1" ]; then
    ARGS="${ARGS} --debug"
    echo "[INFO] PAM debug mode enabled (skip backup/deletion)"
    if [ -n "${DEBUG_USER_ID:-}" ]; then
      ARGS="${ARGS} --debug-user-id ${DEBUG_USER_ID}"
      echo "[INFO] Reusing debug user_id=${DEBUG_USER_ID}"
    fi
  fi

  echo ""
  echo "Running: python /task_data/run_memtrack_pam_v2.py ${ARGS}"
  echo "========================================"
  echo ""

  python /task_data/run_memtrack_pam_v2.py ${ARGS}

  echo ""
  echo "========================================"
  echo "pam_v2 evaluation completed!"
  echo "========================================"
  echo ""
  echo "Predictions and evaluation results saved to /task_logs/"
  exit 0
fi

# ============================================================
# Branch: Original Claude Code Agent (AGENT=claude or unset)
# ============================================================

# Get configs from (in priority order):
# 1. Environment variable TASK_CONFIGS (comma-separated)
# 2. Command line arguments
# 3. Default (config_1)
if [ -n "${TASK_CONFIGS:-}" ]; then
  CONFIGS=$(echo "$TASK_CONFIGS" | tr ',' ' ')
  echo "[DEBUG] Using TASK_CONFIGS env var: $TASK_CONFIGS"
  echo "[DEBUG] Parsed as: $CONFIGS"
elif [ $# -gt 0 ]; then
  CONFIGS="$@"
  echo "[DEBUG] Using command line args: $CONFIGS"
else
  CONFIGS="config_1"
  echo "[DEBUG] No TASK_CONFIGS env var or args provided, using default: $CONFIGS"
fi

echo "========================================"
echo "Claude Code Agent Execution"
echo "========================================"
echo "Configs to run: $CONFIGS"
echo ""

IFS=' ' read -ra CONFIG_ARRAY <<< "$CONFIGS"
echo "[DEBUG] Number of configs to process: ${#CONFIG_ARRAY[@]}"
for i in "${!CONFIG_ARRAY[@]}"; do
  echo "[DEBUG] Config $((i+1)): '${CONFIG_ARRAY[i]}'"
done
echo ""

for CONFIG_NAME in "${CONFIG_ARRAY[@]}"; do
  if [[ "$CONFIG_NAME" == *.yaml ]]; then
    CONFIG_FILE="/task_data/test_configs/$CONFIG_NAME"
  else
    CONFIG_FILE="/task_data/test_configs/${CONFIG_NAME}.yaml"
  fi

  if [ ! -f "$CONFIG_FILE" ]; then
    echo "ERROR: Config file not found: $CONFIG_FILE"
    echo "Available configs:"
    ls -1 /task_data/test_configs/*.yaml 2>/dev/null | sed 's|/task_data/test_configs/||' | sed 's|\.yaml||' || echo "  (none found)"
    exit 1
  fi

  echo "========================================"
  echo "Running task for: $CONFIG_NAME"
  echo "Config file: $CONFIG_FILE"
  echo "========================================"

  if [ "$DEBUG" = "true" ] || [ "$DEBUG" = "1" ]; then
    echo ""
    echo "⚠ DEBUG MODE ENABLED: Using stub instead of actual agent"
    echo ""
    STUB_MODE=true /task_data/setup_and_run.sh "$CONFIG_FILE"
  else
    /task_data/setup_and_run.sh "$CONFIG_FILE"
  fi

  echo ""
  echo "Completed: $CONFIG_NAME"
  echo ""
done

echo "========================================"
echo "All tasks completed!"
echo "========================================"
echo ""
echo "Note: Each config was evaluated immediately after execution."
echo "Results have been saved to MongoDB (if configured)."
