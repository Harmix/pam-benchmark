#!/bin/bash
set -e

# Usage: 
#   - Via environment variable: BENCHMARK_CONFIGS="config_1 config_2" solve.sh
#   - Via command line args: solve.sh config_1 config_2
#   - Default: runs config_1 if neither provided
# Examples:
#   BENCHMARK_CONFIGS="config_1 config_2" solve.sh
#   solve.sh config_1 config_2 config_3
#   solve.sh config_vg_15

# Source secrets.env if available (for non-interactive Harbor runs)
if [ -f /workspace/secrets.env ]; then
  set -a
  source /workspace/secrets.env
  set +a
fi

# Debug: Show environment variable value
echo "[DEBUG] BENCHMARK_CONFIGS='${BENCHMARK_CONFIGS:-}'"
echo "[DEBUG] Command line args: $@"
echo "[DEBUG] Number of args: $#"
echo "[DEBUG] Current directory: $(pwd)"
echo "[DEBUG] Checking for benchmark_configs.txt in common locations..."

# Debug: List files in workspace and current directory
echo "[DEBUG] Files in /workspace/:"
ls -la /workspace/ 2>/dev/null | head -10 || echo "  (cannot list /workspace/)"
echo "[DEBUG] Files in current directory:"
ls -la . 2>/dev/null | head -10 || echo "  (cannot list current directory)"

# Get configs from (in priority order):
# 1. Environment variable BENCHMARK_CONFIGS
# 2. File benchmark_configs.txt (check multiple possible locations)
# 3. Command line arguments
# 4. Default (config_1)
CONFIG_FILE=""
if [ -n "${BENCHMARK_CONFIGS:-}" ]; then
  CONFIGS="$BENCHMARK_CONFIGS"
  echo "[DEBUG] Using BENCHMARK_CONFIGS env var: $CONFIGS"
else
  # Try to find benchmark_configs.txt in multiple locations
  # Harbor mounts solution/ directory, so check there first
  POSSIBLE_PATHS=(
    "/workspace/solution/benchmark_configs.txt"
    "/solution/benchmark_configs.txt"
    "/workspace/benchmark_configs.txt"
    "./benchmark_configs.txt"
    "benchmark_configs.txt"
    "$(pwd)/benchmark_configs.txt"
  )
  
  for path in "${POSSIBLE_PATHS[@]}"; do
    if [ -f "$path" ]; then
      CONFIG_FILE="$path"
      echo "[DEBUG] Found benchmark_configs.txt at: $path"
      break
    else
      echo "[DEBUG] Not found: $path"
    fi
  done
  
  if [ -n "$CONFIG_FILE" ]; then
    # Read configs from file, handling both newline-separated and space-separated formats
    echo "[DEBUG] Reading from: $CONFIG_FILE"
    echo "[DEBUG] File size: $(wc -c < "$CONFIG_FILE" 2>/dev/null || echo 0) bytes"
    echo "[DEBUG] File contents:"
    cat "$CONFIG_FILE" | sed 's/^/  /' || echo "  (error reading file)"
    
    # Check if file has any non-whitespace content
    FILE_CONTENT=$(cat "$CONFIG_FILE" | grep -v '^#' | grep -v '^$' | tr '\n' ' ' | sed 's/[[:space:]]\+/ /g' | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')
    echo "[DEBUG] Parsed configs: '$FILE_CONTENT'"
    
    if [ -z "$FILE_CONTENT" ]; then
      echo "[WARNING] $CONFIG_FILE exists but is empty or only contains comments"
      echo "[WARNING] This might mean:"
      echo "[WARNING]   1. The file wasn't created before Harbor ran"
      echo "[WARNING]   2. Harbor is using a cached image with an empty file"
      echo "[WARNING]   3. The file wasn't mounted correctly"
      echo "[WARNING] Using default: config_1"
      echo "[WARNING] To fix: Rebuild the Docker image with --force-build flag"
      CONFIGS="config_1"
    else
      CONFIGS="$FILE_CONTENT"
    fi
  elif [ $# -gt 0 ]; then
    CONFIGS="$@"
    echo "[DEBUG] Using command line args: $CONFIGS"
  else
    CONFIGS="config_1"
    echo "[DEBUG] No config file found and no args provided, using default: $CONFIGS"
  fi
fi

echo "========================================"
echo "PAM Benchmark Execution"
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
    CONFIG_FILE="/benchmark_data/test_configs/$CONFIG_NAME"
  else
    CONFIG_FILE="/benchmark_data/test_configs/${CONFIG_NAME}.yaml"
  fi
  
  # Check if config file exists
  if [ ! -f "$CONFIG_FILE" ]; then
    echo "ERROR: Config file not found: $CONFIG_FILE"
    echo "Available configs:"
    ls -1 /benchmark_data/test_configs/*.yaml 2>/dev/null | sed 's|/benchmark_data/test_configs/||' | sed 's|\.yaml||' || echo "  (none found)"
    exit 1
  fi
  
  echo "========================================"
  echo "Running benchmark for: $CONFIG_NAME"
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
    # Stub mode: use oracle file instead of running actual benchmark
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
      echo "⚠ STUB MODE: Using oracle file instead of running benchmark"
      echo "Oracle file: $ORACLE_FILE"
      STUB_MODE=true ORACLE_FILE="$ORACLE_FILE" /benchmark_data/setup_and_run.sh "$CONFIG_FILE"
    else
      echo "Warning: STUB_MODE enabled but oracle file not found"
      echo "Attempted paths: ${POSSIBLE_ORACLE_PATHS[*]}"
      echo "Falling back to normal mode..."
      /benchmark_data/setup_and_run.sh "$CONFIG_FILE"
    fi
  else
    # Normal mode: run the actual benchmark
    /benchmark_data/setup_and_run.sh "$CONFIG_FILE"
  fi
  
  echo ""
  echo "Completed: $CONFIG_NAME"
  echo ""
done

echo "========================================"
echo "All benchmarks completed!"
echo "========================================"
echo ""
echo "Note: Each config was evaluated immediately after execution."
echo "Results have been saved to MongoDB (if configured)."
echo ""
echo "========================================"
echo "All tasks completed!"
echo "========================================"
