#!/bin/bash
set -e

# Usage: 
#   - Via environment variable: TASK_CONFIGS="config_1,config_2" solve.sh (comma-separated)
#   - Via command line args: solve.sh config_1 config_2
#   - Default: runs config_1 if neither provided
# Examples:
#   TASK_CONFIGS="config_1,config_2" solve.sh
#   TASK_CONFIGS=config_vg_15 solve.sh
#   solve.sh config_1 config_2 config_3

# Source secrets.env if available (for non-interactive Harbor runs)
if [ -f /workspace/secrets.env ]; then
  set -a
  source /workspace/secrets.env
  set +a
fi

# Debug: Show environment variable value
echo "[DEBUG] TASK_CONFIGS='${TASK_CONFIGS:-}'"
echo "[DEBUG] EXPERIMENT_NAME='${EXPERIMENT_NAME:-}'"
echo "[DEBUG] Command line args: $@"
echo "[DEBUG] Number of args: $#"

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
  
  # Check if stub mode is enabled (only via environment variable or explicitly created file)
  # Stub mode should ONLY be enabled if explicitly requested, not by leftover files
  STUB_MODE_ENABLED=false
  ORACLE_FILE=""
  
  # Check environment variable first (highest priority)
  if [ "${STUB_MODE:-false}" = "true" ] || [ "${STUB_MODE:-false}" = "1" ]; then
    STUB_MODE_ENABLED=true
    echo "[DEBUG] Stub mode enabled via STUB_MODE environment variable"
  else
    # Only check for stub mode file if environment variable is not explicitly false
    # This allows file-based stub mode when Harbor doesn't pass env vars
    STUB_MODE_FILE_PATHS=(
      "/workspace/solution/stub_mode.txt"
      "/solution/stub_mode.txt"
      "/workspace/stub_mode.txt"
    )
    
    for stub_file in "${STUB_MODE_FILE_PATHS[@]}"; do
      if [ -f "$stub_file" ]; then
        STUB_MODE_ENABLED=true
        echo "[DEBUG] Found stub mode file at: $stub_file"
        break
      fi
    done
  fi
  
  if [ "$STUB_MODE_ENABLED" = "true" ]; then
    # Stub mode: use oracle file instead of running actual task
    ORACLE_FILE="${ORACLE_FILE:-}"
    
    if [ -z "$ORACLE_FILE" ]; then
      # Try to find oracle file in common locations (Harbor mounts solution/ directory)
      POSSIBLE_ORACLE_PATHS=(
        "/workspace/solution/oracle.txt"
        "/solution/oracle.txt"
        "/workspace/oracle.txt"
        "./oracle.txt"
        "oracle.txt"
      )
      
      for path in "${POSSIBLE_ORACLE_PATHS[@]}"; do
        if [ -f "$path" ]; then
          ORACLE_FILE="$path"
          echo "[DEBUG] Found oracle file at: $path"
          break
        fi
      done
    fi
    
    if [ -n "$ORACLE_FILE" ] && [ -f "$ORACLE_FILE" ]; then
      echo "⚠ STUB MODE: Using oracle file instead of running task"
      echo "Oracle file: $ORACLE_FILE"
      STUB_MODE=true ORACLE_FILE="$ORACLE_FILE" /task_data/setup_and_run.sh "$CONFIG_FILE"
    else
      echo "Warning: STUB_MODE enabled but oracle file not found"
      echo "Attempted paths: ${POSSIBLE_ORACLE_PATHS[*]}"
      echo "Falling back to normal mode..."
      /task_data/setup_and_run.sh "$CONFIG_FILE"
    fi
  else
    # Normal mode: run the actual task
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
