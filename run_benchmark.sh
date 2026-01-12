#!/bin/bash

set -e

# Script to run Harbor benchmarks with config selection
# Usage: ./run_benchmark.sh [config1] [config2] ... [harbor-args...]

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
    if [ -d "$BENCHMARK_DIR/environment/test_configs" ]; then
        ls -1 "$BENCHMARK_DIR/environment/test_configs"/*.yaml 2>/dev/null | \
            sed "s|$BENCHMARK_DIR/environment/test_configs/||" | \
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
    config_file="$BENCHMARK_DIR/environment/test_configs/${config_name}.yaml"
    
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
echo ""
echo "File location: $(realpath "$CONFIG_FILE")"
echo "File size: $(wc -c < "$CONFIG_FILE") bytes"

# Check if Harbor is available
if ! command -v harbor &> /dev/null; then
    echo ""
    echo "Error: 'harbor' command not found."
    echo "Please install Harbor framework or ensure it's in your PATH."
    exit 1
fi

# Build Harbor command
HARBOR_CMD=("harbor" "run" "-p" "$BENCHMARK_DIR")

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

# Show final command
echo ""
echo "=========================================="
echo "Starting Harbor with configs:"
cat "$CONFIG_FILE" | sed 's/^/  - /'
echo "=========================================="
echo ""
echo "Note: If Harbor uses a cached image, you may need to rebuild:"
echo "  Add --force-build flag to force Docker image rebuild"
echo ""
echo "Command: ${HARBOR_CMD[*]}"
echo ""

# Check if --force-build is in the args, if not, suggest it
if [[ ! " ${HARBOR_ARGS[@]} " =~ " --force-build " ]] && [[ ! " ${HARBOR_ARGS[@]} " =~ " --no-force-build " ]]; then
    echo "Tip: Consider adding --force-build to ensure the config file is mounted correctly"
    echo ""
fi

# Execute Harbor
exec "${HARBOR_CMD[@]}"
