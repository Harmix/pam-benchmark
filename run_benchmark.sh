#!/bin/bash

set -e

# Script to run Harbor benchmarks with config selection
# Usage: ./run_benchmark.sh [config1] [config2] ... [harbor-args...]
# 
# This script runs Harbor with the memtrack dataset:
#   harbor run -d "memtrack@1.0" -a oracle -m <model> --registry-path "datasets/memtrack/registry.json"
# 
# Stub mode (for debugging):
#   STUB_MODE=true ORACLE_FILE=./jobs/2026-01-12__11-08-06/benchmark__b9NqGZ2/agent/oracle.txt ./run_benchmark.sh config_1

BENCHMARK_DIR="benchmark"
# Harbor mounts solution/ directory, so put config file there
CONFIG_FILE="$BENCHMARK_DIR/solution/benchmark_configs.txt"

# Function to show usage
show_usage() {
    echo "Usage: $0 [config1] [config2] ... [harbor-args...]"
    echo ""
    echo "Examples:"
    echo "  $0 config_1 config_2                    # Run config_1 and config_2"
    echo "  $0 config_1 config_2 -a oracle -m claude-3-5-sonnet-20241022"
    echo "  $0                                      # Interactive mode - will prompt for configs"
    echo ""
    echo "Available configs:"
    if [ -d "datasets/memtrack/test_configs" ]; then
        ls -1 "datasets/memtrack/test_configs"/*.yaml 2>/dev/null | \
            sed "s|datasets/memtrack/test_configs/||" | \
            sed 's|\.yaml||' | \
            head -20
        echo "..."
    else
        echo "  (config directory not found)"
    fi
}

# Check if benchmark directory exists
if [ ! -d "$BENCHMARK_DIR" ]; then
    echo "Error: Benchmark directory '$BENCHMARK_DIR' not found."
    echo "Please run this script from the project root directory."
    exit 1
fi

# Parse arguments
CONFIGS=()
HARBOR_ARGS=()
IN_HARBOR_ARGS=false

for arg in "$@"; do
    if [[ "$arg" == -* ]] || [ "$IN_HARBOR_ARGS" = true ]; then
        # This is a Harbor argument
        IN_HARBOR_ARGS=true
        HARBOR_ARGS+=("$arg")
    else
        # This is a config name
        CONFIGS+=("$arg")
    fi
done

# If no configs provided, prompt interactively
if [ ${#CONFIGS[@]} -eq 0 ]; then
    echo "=========================================="
    echo "Harbor Benchmark Runner"
    echo "=========================================="
    echo ""
    echo "Enter config names (space-separated) or press Enter for default (config_1):"
    echo "Example: config_1 config_2 config_vg_15"
    echo ""
    read -p "Configs: " input_configs
    
    if [ -n "$input_configs" ]; then
        # Parse the input into an array
        read -ra CONFIGS <<< "$input_configs"
    else
        CONFIGS=("config_1")
        echo "Using default: config_1"
    fi
fi

# Validate configs exist
echo ""
echo "Validating configs..."
VALID_CONFIGS=()
for config in "${CONFIGS[@]}"; do
    # Remove .yaml extension if present
    config_name="${config%.yaml}"
    config_file="datasets/memtrack/test_configs/${config_name}.yaml"
    
    if [ -f "$config_file" ]; then
        VALID_CONFIGS+=("$config_name")
        echo "  ✓ $config_name"
    else
        echo "  ✗ $config_name (not found)"
        echo "    Expected: $config_file"
    fi
done

if [ ${#VALID_CONFIGS[@]} -eq 0 ]; then
    echo ""
    echo "Error: No valid configs found!"
    show_usage
    exit 1
fi

# Write configs to file
echo ""
echo "Writing configs to $CONFIG_FILE..."
printf "%s\n" "${VALID_CONFIGS[@]}" > "$CONFIG_FILE"

# Verify file was created and has content
if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: Failed to create $CONFIG_FILE"
    exit 1
fi

FILE_CONTENT=$(cat "$CONFIG_FILE" | grep -v '^#' | grep -v '^$' | tr '\n' ' ' | sed 's/[[:space:]]*$//')
if [ -z "$FILE_CONTENT" ]; then
    echo "Error: $CONFIG_FILE is empty after writing!"
    exit 1
fi

echo "Configs written successfully:"
cat "$CONFIG_FILE" | sed 's/^/  /'

# Check if Harbor is available
if ! command -v harbor &> /dev/null; then
    echo ""
    echo "Error: 'harbor' command not found."
    echo "Please install Harbor framework or ensure it's in your PATH."
    exit 1
fi

# Prepare dataset for Docker build
# This copies the dataset into benchmark/datasets/ so it's available in the Docker build context
PREPARE_BUILD_SCRIPT="$BENCHMARK_DIR/prepare_build.sh"
if [ -f "$PREPARE_BUILD_SCRIPT" ]; then
    echo ""
    echo "Preparing dataset for Docker build..."
    bash "$PREPARE_BUILD_SCRIPT"
    if [ $? -ne 0 ]; then
        echo "Error: Failed to prepare dataset for build"
        exit 1
    fi
    echo "Dataset prepared successfully"
    echo ""
else
    echo "Warning: prepare_build.sh not found at $PREPARE_BUILD_SCRIPT"
    echo "Dataset may not be available in Docker build context"
    echo ""
fi

# Build Harbor command
HARBOR_CMD=("harbor" "run" "-p" "$BENCHMARK_DIR")

# Add dataset registry path to use memtrack dataset
REGISTRY_PATH="datasets/memtrack/registry.json"
if [ -f "$REGISTRY_PATH" ]; then
    HARBOR_CMD+=("--registry-path" "$REGISTRY_PATH")
else
    echo "Warning: Dataset registry not found at $REGISTRY_PATH"
fi

# Add --force-build by default to ensure config file is picked up
# User can override with --no-force-build if needed
if [[ ! " ${HARBOR_ARGS[@]} " =~ " --no-force-build " ]]; then
    HARBOR_CMD+=("--force-build")
fi

# Add Harbor arguments if provided
if [ ${#HARBOR_ARGS[@]} -gt 0 ]; then
    HARBOR_CMD+=("${HARBOR_ARGS[@]}")
fi

# If no agent/model specified, prompt for them
if [[ ! " ${HARBOR_ARGS[@]} " =~ " -a " ]] && [[ ! " ${HARBOR_ARGS[@]} " =~ " --agent " ]]; then
    echo ""
    echo "Agent not specified. Enter agent name (or press Enter for 'oracle'):"
    read -p "Agent [oracle]: " agent_input
    agent="${agent_input:-oracle}"
    HARBOR_CMD+=("-a" "$agent")
fi

if [[ ! " ${HARBOR_ARGS[@]} " =~ " -m " ]] && [[ ! " ${HARBOR_ARGS[@]} " =~ " --model " ]]; then
    echo ""
    echo "Model not specified. Enter model name (or press Enter to skip):"
    read -p "Model: " model_input
    if [ -n "$model_input" ]; then
        HARBOR_CMD+=("-m" "$model_input")
    fi
fi

# Handle stub mode - only enable if explicitly requested
STUB_MODE_FILE="$BENCHMARK_DIR/solution/stub_mode.txt"
ORACLE_DEST="$BENCHMARK_DIR/solution/oracle.txt"

# Clean up any existing stub mode files from previous runs
if [ -f "$STUB_MODE_FILE" ]; then
    rm -f "$STUB_MODE_FILE"
fi
if [ -f "$ORACLE_DEST" ]; then
    rm -f "$ORACLE_DEST"
fi

# Clean up experiment name file from previous runs
EXPERIMENT_NAME_FILE="$BENCHMARK_DIR/solution/experiment_name.txt"
if [ -f "$EXPERIMENT_NAME_FILE" ]; then
    rm -f "$EXPERIMENT_NAME_FILE"
fi

# Only enable stub mode if explicitly set
if [ "${STUB_MODE:-false}" = "true" ] || [ "${STUB_MODE:-false}" = "1" ]; then
    ORACLE_FILE="${ORACLE_FILE:-}"
    if [ -z "$ORACLE_FILE" ]; then
        echo ""
        echo "Error: STUB_MODE enabled but ORACLE_FILE not set"
        echo "Usage: STUB_MODE=true ORACLE_FILE=./jobs/2026-01-12__11-08-06/benchmark__b9NqGZ2/agent/oracle.txt ./run_benchmark.sh config_1"
        exit 1
    fi
    
    if [ ! -f "$ORACLE_FILE" ]; then
        echo ""
        echo "Error: Oracle file not found: $ORACLE_FILE"
        exit 1
    fi
    
    # Copy oracle file to solution directory so Harbor can mount it
    echo ""
    echo "⚠ STUB MODE ENABLED"
    echo "Oracle file: $ORACLE_FILE"
    echo "Copying to: $ORACLE_DEST (for Harbor mounting)"
    cp "$ORACLE_FILE" "$ORACLE_DEST"
    # Create stub mode flag file
    echo "stub_mode_enabled" > "$STUB_MODE_FILE"
    echo "Created stub mode flag: $STUB_MODE_FILE"
    echo "This will create logs from oracle file instead of running benchmarks"
    echo ""
else
    # Ensure stub mode is disabled (clean up any leftover files)
    if [ -f "$STUB_MODE_FILE" ]; then
        rm -f "$STUB_MODE_FILE"
    fi
    if [ -f "$ORACLE_DEST" ]; then
        rm -f "$ORACLE_DEST"
    fi
fi

# Show final command
echo ""
echo "=========================================="
echo "Starting Harbor with configs:"
cat "$CONFIG_FILE" | sed 's/^/  - /'
echo "=========================================="
echo ""
echo "Harbor command: ${HARBOR_CMD[*]}"
echo ""
echo "Note: Using memtrack dataset via --registry-path"
echo ""

# Generate experiment name if not provided
if [ -z "${EXPERIMENT_NAME:-}" ]; then
    # Generate a unique experiment name based on timestamp and configs
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    CONFIG_SUMMARY=$(cat "$CONFIG_FILE" | tr '\n' '_' | sed 's/_$//' | tr ' ' '_' | head -c 50)
    EXPERIMENT_NAME="experiment_${TIMESTAMP}_${CONFIG_SUMMARY}"
    export EXPERIMENT_NAME
    echo "Generated experiment name: $EXPERIMENT_NAME"
fi

# Save experiment name to a file so it can be read inside the container
# Harbor mounts solution/ directory, so put it there
EXPERIMENT_NAME_FILE="$BENCHMARK_DIR/solution/experiment_name.txt"
echo "$EXPERIMENT_NAME" > "$EXPERIMENT_NAME_FILE"
echo "Saved experiment name to: $EXPERIMENT_NAME_FILE"

# Export stub mode and oracle file for Harbor to pass to container
if [ "${STUB_MODE:-false}" = "true" ] || [ "${STUB_MODE:-false}" = "1" ]; then
    export STUB_MODE=true
    export ORACLE_FILE
    echo "Stub mode environment variables will be passed to container"
    echo ""
fi

# Export experiment name and Harbor project name for Harbor to pass to container
export EXPERIMENT_NAME
export HARBOR_PROJECT_NAME="$BENCHMARK_DIR"  # "benchmark"

# Execute Harbor
exec "${HARBOR_CMD[@]}"
