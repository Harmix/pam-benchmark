#!/bin/bash

# =============================================================================
# run_parallel_harbor.sh
# 
# Script to run multiple Harbor commands in parallel with configurable concurrency.
# Each config gets its own Harbor run, and the script manages parallel execution
# according to the specified max concurrent jobs.
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
N_CONCURRENT=2
FORCE_BUILD=false
EXTRA_ARGS=""

# =============================================================================
# Functions
# =============================================================================

print_usage() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS]

Run multiple Harbor commands in parallel with configurable concurrency.

Required Arguments:
    -e, --experiment-name NAME    Name of the experiment
    -c, --configs CONFIGS         Comma-separated list of config names (without .yaml extension)
                                  Example: "config_1,config_2,config_3"
    -d, --dataset NAME            Dataset name with version (e.g., "memtrack@1.0")
    -r, --registry-path PATH      Path to the registry.json file

Optional Arguments:
    -n, --n-concurrent NUM        Maximum number of concurrent jobs (default: 2)
    -f, --force-build             Add --force-build flag to harbor commands
    --extra-args ARGS             Additional arguments to pass to harbor run
    -h, --help                    Show this help message

Example:
    $(basename "$0") \\
        -e my_experiment \\
        -c "config_1,config_2,config_3,config_4,config_5" \\
        -d "memtrack@1.0" \\
        -r "datasets/memtrack/registry.json" \\
        -n 3 \\
        -f

    This will run 5 configs with max 3 running concurrently.

EOF
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to run a single harbor command
run_harbor_config() {
    local config="$1"
    local experiment_name="$2"
    local dataset="$3"
    local registry_path="$4"
    local force_build="$5"
    local extra_args="$6"
    local log_file="$7"
    
    local cmd="EXPERIMENT_NAME=${experiment_name} TASK_CONFIGS=${config} harbor run -d ${dataset} --registry-path ${registry_path}"
    
    if [ "$force_build" = true ]; then
        cmd="${cmd} --force-build"
    fi
    
    if [ -n "$extra_args" ]; then
        cmd="${cmd} ${extra_args}"
    fi
    
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting: ${config}" >> "$log_file"
    echo "Command: ${cmd}" >> "$log_file"
    echo "---" >> "$log_file"
    
    # Execute the command and capture output
    local exit_code=0
    eval "$cmd" >> "$log_file" 2>&1 || exit_code=$?
    
    # Check for harbor command failure
    if [ $exit_code -ne 0 ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Failed (exit code $exit_code): ${config}" >> "$log_file"
        return 1
    fi
    
    # Check for Harbor-specific failures in output (harbor often returns 0 even on task failures)
    # Look for indicators of failure: Errors > 0, Mean: 0.000 with errors, or exception distributions
    if grep -q "│ Errors[[:space:]]*│[[:space:]]*[1-9]" "$log_file" 2>/dev/null; then
        # Found errors in the result table
        local error_count=$(grep -o "│ Errors[[:space:]]*│[[:space:]]*[0-9]*" "$log_file" | grep -o "[0-9]*$" | tail -1)
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Failed (Harbor reported $error_count error(s)): ${config}" >> "$log_file"
        return 1
    fi
    
    # Check for Mean: 0.000 which typically indicates failure (unless Trials is also 0)
    if grep -q "│ Mean[[:space:]]*│[[:space:]]*0\.000" "$log_file" 2>/dev/null; then
        # Check if there were actual trials
        local trials=$(grep -o "│ Trials[[:space:]]*│[[:space:]]*[0-9]*" "$log_file" | grep -o "[0-9]*$" | tail -1)
        if [ -n "$trials" ] && [ "$trials" -eq 0 ]; then
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] Failed (No successful trials): ${config}" >> "$log_file"
            return 1
        fi
    fi
    
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Completed successfully: ${config}" >> "$log_file"
    return 0
}

# =============================================================================
# Parse Arguments
# =============================================================================

while [[ $# -gt 0 ]]; do
    case $1 in
        -e|--experiment-name)
            EXPERIMENT_NAME="$2"
            shift 2
            ;;
        -c|--configs)
            CONFIGS="$2"
            shift 2
            ;;
        -d|--dataset)
            DATASET="$2"
            shift 2
            ;;
        -r|--registry-path)
            REGISTRY_PATH="$2"
            shift 2
            ;;
        -n|--n-concurrent)
            N_CONCURRENT="$2"
            shift 2
            ;;
        -f|--force-build)
            FORCE_BUILD=true
            shift
            ;;
        --extra-args)
            EXTRA_ARGS="$2"
            shift 2
            ;;
        -h|--help)
            print_usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            print_usage
            exit 1
            ;;
    esac
done

# =============================================================================
# Validate Required Arguments
# =============================================================================

if [ -z "$EXPERIMENT_NAME" ]; then
    log_error "Experiment name is required (-e/--experiment-name)"
    print_usage
    exit 1
fi

if [ -z "$CONFIGS" ]; then
    log_error "Configs are required (-c/--configs)"
    print_usage
    exit 1
fi

if [ -z "$DATASET" ]; then
    log_error "Dataset is required (-d/--dataset)"
    print_usage
    exit 1
fi

if [ -z "$REGISTRY_PATH" ]; then
    log_error "Registry path is required (-r/--registry-path)"
    print_usage
    exit 1
fi

# =============================================================================
# Setup
# =============================================================================

# Create logs directory
LOGS_DIR="logs/parallel_harbor_runs/${EXPERIMENT_NAME}_$(date '+%Y%m%d_%H%M%S')"
mkdir -p "$LOGS_DIR"

# Parse configs into array
IFS=',' read -ra CONFIG_ARRAY <<< "$CONFIGS"
TOTAL_CONFIGS=${#CONFIG_ARRAY[@]}

log_info "=========================================="
log_info "Parallel Harbor Runner"
log_info "=========================================="
log_info "Experiment Name: $EXPERIMENT_NAME"
log_info "Dataset: $DATASET"
log_info "Registry Path: $REGISTRY_PATH"
log_info "Total Configs: $TOTAL_CONFIGS"
log_info "Max Concurrent: $N_CONCURRENT"
log_info "Force Build: $FORCE_BUILD"
log_info "Extra Args: $EXTRA_ARGS"
log_info "Logs Directory: $LOGS_DIR"
log_info "=========================================="
echo ""

# Arrays to track jobs
declare -a PIDS=()
declare -a CONFIGS_RUNNING=()
declare -a COMPLETED_CONFIGS=()
declare -a FAILED_CONFIGS=()

# =============================================================================
# Main Execution Loop
# =============================================================================

config_index=0
completed_count=0
failed_count=0

# Function to check and clean up finished jobs
check_finished_jobs() {
    local new_pids=()
    local new_configs=()
    
    for i in "${!PIDS[@]}"; do
        local pid="${PIDS[$i]}"
        local config="${CONFIGS_RUNNING[$i]}"
        
        if ! kill -0 "$pid" 2>/dev/null; then
            # Process finished, check exit status
            wait "$pid"
            local exit_code=$?
            
            if [ $exit_code -eq 0 ]; then
                log_success "Config '$config' completed successfully"
                COMPLETED_CONFIGS+=("$config")
                ((completed_count++))
            else
                log_error "Config '$config' failed with exit code $exit_code"
                FAILED_CONFIGS+=("$config")
                ((failed_count++))
            fi
        else
            # Process still running
            new_pids+=("$pid")
            new_configs+=("$config")
        fi
    done
    
    PIDS=("${new_pids[@]}")
    CONFIGS_RUNNING=("${new_configs[@]}")
}

# Function to get current running count
get_running_count() {
    echo "${#PIDS[@]}"
}

log_info "Starting parallel execution..."
echo ""

# Main loop
while [ $config_index -lt $TOTAL_CONFIGS ] || [ "$(get_running_count)" -gt 0 ]; do
    # Check for finished jobs
    check_finished_jobs
    
    # Start new jobs if we have capacity and configs remaining
    while [ $config_index -lt $TOTAL_CONFIGS ] && [ "$(get_running_count)" -lt "$N_CONCURRENT" ]; do
        config="${CONFIG_ARRAY[$config_index]}"
        # Remove .yaml extension if present
        config="${config%.yaml}"
        
        log_file="${LOGS_DIR}/${config}.log"
        
        log_info "Starting config '$config' ($(($config_index + 1))/$TOTAL_CONFIGS) - Running: $(get_running_count)/$N_CONCURRENT"
        
        # Start the job in background
        run_harbor_config "$config" "$EXPERIMENT_NAME" "$DATASET" "$REGISTRY_PATH" "$FORCE_BUILD" "$EXTRA_ARGS" "$log_file" &
        pid=$!
        
        PIDS+=("$pid")
        CONFIGS_RUNNING+=("$config")
        
        ((config_index++))
    done
    
    # If we have running jobs, wait a bit before checking again
    if [ "$(get_running_count)" -gt 0 ]; then
        sleep 2
    fi
done

# =============================================================================
# Summary
# =============================================================================

echo ""
log_info "=========================================="
log_info "Execution Summary"
log_info "=========================================="
log_info "Total Configs: $TOTAL_CONFIGS"
log_success "Completed: $completed_count"

if [ $failed_count -gt 0 ]; then
    log_error "Failed: $failed_count"
    echo ""
    log_error "Failed configs:"
    for config in "${FAILED_CONFIGS[@]}"; do
        echo "  - $config (see ${LOGS_DIR}/${config}.log)"
    done
fi

echo ""
log_info "Logs saved to: $LOGS_DIR"
log_info "=========================================="

# Exit with error if any configs failed
if [ $failed_count -gt 0 ]; then
    exit 1
fi

exit 0
