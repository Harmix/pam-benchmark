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
  
  # Run the benchmark
  /benchmark_data/setup_and_run.sh "$CONFIG_FILE"
  
  echo ""
  echo "Completed: $CONFIG_NAME"
  echo ""
done

echo "========================================"
echo "All benchmarks completed!"
echo "========================================"
