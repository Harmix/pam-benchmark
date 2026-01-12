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

# Get configs from environment variable or command line arguments
# Priority: BENCHMARK_CONFIGS env var > command line args > default (config_1)
if [ -n "${BENCHMARK_CONFIGS:-}" ]; then
  CONFIGS="$BENCHMARK_CONFIGS"
elif [ $# -gt 0 ]; then
  CONFIGS="$@"
else
  CONFIGS="config_1"
fi

echo "========================================"
echo "PAM Benchmark Execution"
echo "========================================"
echo "Configs to run: $CONFIGS"
echo ""

# Run setup_and_run.sh for each config
for CONFIG_NAME in $CONFIGS; do
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
