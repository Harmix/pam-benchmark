#!/bin/bash
set -e

# Usage: 
#   - Via environment variable: TASK_CONFIGS="config_1,config_2" solve.sh (comma-separated)
#   - Via command line args: solve.sh config_1 config_2
#   - Default: runs config_1 if neither provided
# Examples:
#   TASK_CONFIGS="config_1,config_2" solve.sh
#   TASK_CONFIGS=config_vg_15 solve.sh
#   DEBUG=true TASK_CONFIGS=config_1 solve.sh  # Uses stub mode for faster development

# Source secrets.env if available (for non-interactive Harbor runs)
if [ -f /workspace/secrets.env ]; then
  set -a
  source /workspace/secrets.env
  set +a
fi

# Set DEBUG default to false
DEBUG="${DEBUG:-false}"

# Show environment variables
echo "[INFO] TASK_CONFIGS='${TASK_CONFIGS:-}'"
echo "[INFO] EXPERIMENT_NAME='${EXPERIMENT_NAME:-}'"
echo "[INFO] DEBUG='${DEBUG}'"
echo "[INFO] Command line args: $@"

# Get configs from (in priority order):
# 1. Environment variable TASK_CONFIGS (comma-separated)
# 2. Command line arguments
# 3. Default (config_1)
if [ -n "${TASK_CONFIGS:-}" ]; then
  # Convert commas to spaces for internal processing
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
echo "PAM Task Execution"
echo "========================================"
echo "Configs to run: $CONFIGS"
echo ""

# Convert CONFIGS to array to handle spaces properly
# This ensures multiple configs are processed correctly
IFS=' ' read -ra CONFIG_ARRAY <<< "$CONFIGS"
echo "[DEBUG] Number of configs to process: ${#CONFIG_ARRAY[@]}"
for i in "${!CONFIG_ARRAY[@]}"; do
  echo "[DEBUG] Config $((i+1)): '${CONFIG_ARRAY[i]}'"
done
echo ""

# Run setup_and_run.sh for each config
# Use array to properly handle spaces in config names
for CONFIG_NAME in "${CONFIG_ARRAY[@]}"; do
  # Convert config name to full path
  # Handle both "config_1" and "config_1.yaml" formats
  if [[ "$CONFIG_NAME" == *.yaml ]]; then
    CONFIG_FILE="/task_data/test_configs/$CONFIG_NAME"
  else
    CONFIG_FILE="/task_data/test_configs/${CONFIG_NAME}.yaml"
  fi
  
  # Check if config file exists
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
  
  # Check if DEBUG mode is enabled (uses stub to skip actual agent execution)
  # DEBUG=true enables stub mode for faster development iteration
  if [ "$DEBUG" = "true" ] || [ "$DEBUG" = "1" ]; then
    echo ""
    echo "⚠ DEBUG MODE ENABLED: Using stub instead of actual agent"
    echo ""
    
    # In debug mode, pass STUB_MODE=true to setup_and_run.sh
    # The stub mode will generate mock outputs for faster development
    STUB_MODE=true /task_data/setup_and_run.sh "$CONFIG_FILE"
  else
    # Normal mode: run the actual task with the agent
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
