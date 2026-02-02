#!/bin/bash

# =============================================================================
# run_parallel_harbor.sh (LoCoMo)
# 
# Script to run multiple Harbor commands in parallel for LoCoMo benchmark.
# Each sample gets its own Harbor container, enabling parallel evaluation.
#
# IMPORTANT: To avoid Docker build conflicts, the script:
#   1. First builds the image once with --force-build (if -f flag is set)
#   2. Then runs all samples in parallel WITHOUT --force-build
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default values
N_CONCURRENT=2
FORCE_BUILD=false
MODEL="pam"
MAX_QUESTIONS=0
EXTRA_ARGS=""
SAMPLE_INDICES="0,1,2,3,4,5,6,7,8,9"  # All 10 samples by default

# Global start time
SCRIPT_START_TIME=$(date +%s)

# =============================================================================
# Functions
# =============================================================================

print_usage() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS]

Run multiple Harbor commands in parallel for LoCoMo benchmark.
Each sample runs in its own container.

Note: Containers are started with a 1-second delay between each to avoid
Docker build conflicts when using --force-build.

Required Arguments:
    -e, --experiment-name NAME    Name of the experiment (same for all samples)

Optional Arguments:
    -s, --samples INDICES         Comma-separated list of sample indices (default: 0,1,2,3,4,5,6,7,8,9)
    -m, --model MODEL             Model to use (default: pam)
    -q, --max-questions NUM       Max questions per sample (default: 0 = all)
    -n, --n-concurrent NUM        Maximum number of concurrent jobs (default: 2)
    -f, --force-build             Add --force-build flag to harbor commands
    --extra-args ARGS             Additional arguments to pass to harbor run
    -h, --help                    Show this help message

Example (run all 10 samples with 10 concurrent):
    $(basename "$0") \\
        -e locomo_pam_full \\
        -n 10 \\
        -f

Example (run samples 0-4 with PAM, 10 questions each):
    $(basename "$0") \\
        -e locomo_pam_test \\
        -s "0,1,2,3,4" \\
        -q 10 \\
        -n 3 \\
        -f

EOF
}

# Format seconds to human readable time
format_duration() {
    local seconds=$1
    local hours=$((seconds / 3600))
    local minutes=$(((seconds % 3600) / 60))
    local secs=$((seconds % 60))
    
    if [ $hours -gt 0 ]; then
        printf "%dh %dm %ds" $hours $minutes $secs
    elif [ $minutes -gt 0 ]; then
        printf "%dm %ds" $minutes $secs
    else
        printf "%ds" $secs
    fi
}

# Get elapsed time since script start
get_elapsed_time() {
    local now=$(date +%s)
    local elapsed=$((now - SCRIPT_START_TIME))
    format_duration $elapsed
}

log_info() {
    local elapsed=$(get_elapsed_time)
    echo -e "${BLUE}[INFO]${NC} [${CYAN}${elapsed}${NC}] $1"
}

log_success() {
    local elapsed=$(get_elapsed_time)
    echo -e "${GREEN}[SUCCESS]${NC} [${CYAN}${elapsed}${NC}] $1"
}

log_warning() {
    local elapsed=$(get_elapsed_time)
    echo -e "${YELLOW}[WARNING]${NC} [${CYAN}${elapsed}${NC}] $1"
}

log_error() {
    local elapsed=$(get_elapsed_time)
    echo -e "${RED}[ERROR]${NC} [${CYAN}${elapsed}${NC}] $1"
}

# Function to run a single harbor command for a sample
run_harbor_sample() {
    local sample_index="$1"
    local experiment_name="$2"
    local model="$3"
    local max_questions="$4"
    local use_force_build="$5"
    local extra_args="$6"
    local log_file="$7"
    
    # Use the SAME experiment name for all samples
    local cmd="EXPERIMENT_NAME=${experiment_name} MODEL=${model} SAMPLE_INDEX=${sample_index}"
    
    if [ "$max_questions" -gt 0 ]; then
        cmd="${cmd} MAX_QUESTIONS=${max_questions}"
    fi
    
    cmd="${cmd} harbor run -d locomo@1.0 --registry-path datasets/locomo/registry.json"
    
    # Only add force-build if explicitly requested for this run
    if [ "$use_force_build" = true ]; then
        cmd="${cmd} --force-build"
    fi
    
    if [ -n "$extra_args" ]; then
        cmd="${cmd} ${extra_args}"
    fi
    
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting: sample_${sample_index}" >> "$log_file"
    echo "Experiment: ${experiment_name}" >> "$log_file"
    echo "Command: ${cmd}" >> "$log_file"
    echo "---" >> "$log_file"
    
    # Execute the command and capture output
    local exit_code=0
    eval "$cmd" >> "$log_file" 2>&1 || exit_code=$?
    
    # Check for harbor command failure
    if [ $exit_code -ne 0 ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Failed (exit code $exit_code): sample_${sample_index}" >> "$log_file"
        return 1
    fi
    
    # Check for Harbor-specific failures in output
    if grep -q "│ Errors[[:space:]]*│[[:space:]]*[1-9]" "$log_file" 2>/dev/null; then
        local error_count=$(grep -o "│ Errors[[:space:]]*│[[:space:]]*[0-9]*" "$log_file" | grep -o "[0-9]*$" | tail -1)
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Failed (Harbor reported $error_count error(s)): sample_${sample_index}" >> "$log_file"
        return 1
    fi
    
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Completed successfully: sample_${sample_index}" >> "$log_file"
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
        -s|--samples)
            SAMPLE_INDICES="$2"
            shift 2
            ;;
        -m|--model)
            MODEL="$2"
            shift 2
            ;;
        -q|--max-questions)
            MAX_QUESTIONS="$2"
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

# =============================================================================
# Setup
# =============================================================================

# Create logs directory
LOGS_DIR="logs/locomo_parallel/${EXPERIMENT_NAME}_$(date '+%Y%m%d_%H%M%S')"
mkdir -p "$LOGS_DIR"

# Parse sample indices into array
IFS=',' read -ra SAMPLE_ARRAY <<< "$SAMPLE_INDICES"
TOTAL_SAMPLES=${#SAMPLE_ARRAY[@]}

echo ""
log_info "=========================================="
log_info "LoCoMo Parallel Harbor Runner"
log_info "=========================================="
log_info "Experiment Name: $EXPERIMENT_NAME (same for all samples)"
log_info "Model: $MODEL"
log_info "Total Samples: $TOTAL_SAMPLES"
log_info "Sample Indices: $SAMPLE_INDICES"
log_info "Max Questions: ${MAX_QUESTIONS:-all}"
log_info "Max Concurrent: $N_CONCURRENT"
log_info "Force Build: $FORCE_BUILD"
log_info "Extra Args: $EXTRA_ARGS"
log_info "Logs Directory: $LOGS_DIR"
log_info "=========================================="
echo ""

# Arrays to track jobs
declare -a PIDS=()
declare -a SAMPLES_RUNNING=()
declare -a COMPLETED_SAMPLES=()
declare -a FAILED_SAMPLES=()
declare -a SAMPLE_START_TIMES=()

# =============================================================================
# Staggered Start Configuration
# =============================================================================

# Delay between starting new containers to avoid Docker conflicts
START_DELAY_SECONDS=1

if [ "$FORCE_BUILD" = true ]; then
    log_info "Force-build enabled: containers will start with ${START_DELAY_SECONDS}s delay to avoid Docker conflicts"
fi

# =============================================================================
# Main Execution Loop
# =============================================================================

sample_idx=0
completed_count=0
failed_count=0

# Function to check and clean up finished jobs
check_finished_jobs() {
    local new_pids=()
    local new_samples=()
    local new_start_times=()
    
    for i in "${!PIDS[@]}"; do
        local pid="${PIDS[$i]}"
        local sample="${SAMPLES_RUNNING[$i]}"
        local start_time="${SAMPLE_START_TIMES[$i]}"
        
        if ! kill -0 "$pid" 2>/dev/null; then
            # Process finished, check exit status
            wait "$pid"
            local exit_code=$?
            
            # Calculate sample duration
            local end_time=$(date +%s)
            local duration=$((end_time - start_time))
            local duration_str=$(format_duration $duration)
            
            if [ $exit_code -eq 0 ]; then
                log_success "Sample $sample completed (took $duration_str)"
                COMPLETED_SAMPLES+=("$sample")
                ((completed_count++))
            else
                log_error "Sample $sample failed after $duration_str (exit code $exit_code)"
                FAILED_SAMPLES+=("$sample")
                ((failed_count++))
            fi
        else
            # Process still running
            new_pids+=("$pid")
            new_samples+=("$sample")
            new_start_times+=("$start_time")
        fi
    done
    
    PIDS=("${new_pids[@]}")
    SAMPLES_RUNNING=("${new_samples[@]}")
    SAMPLE_START_TIMES=("${new_start_times[@]}")
}

# Function to get current running count
get_running_count() {
    echo "${#PIDS[@]}"
}

# Function to display status
display_status() {
    local running=$(get_running_count)
    local pending=$((TOTAL_SAMPLES - sample_idx))
    
    echo -e "${CYAN}[STATUS]${NC} Elapsed: $(get_elapsed_time) | Running: $running | Completed: $completed_count | Failed: $failed_count | Pending: $pending"
}

log_info "Starting parallel execution..."
echo ""

# Main loop
last_status_time=$(date +%s)
STATUS_INTERVAL=30  # Show status every 30 seconds

while [ $sample_idx -lt $TOTAL_SAMPLES ] || [ "$(get_running_count)" -gt 0 ]; do
    # Check for finished jobs
    check_finished_jobs
    
    # Start new jobs if we have capacity and samples remaining
    while [ $sample_idx -lt $TOTAL_SAMPLES ] && [ "$(get_running_count)" -lt "$N_CONCURRENT" ]; do
        sample_index="${SAMPLE_ARRAY[$sample_idx]}"
        
        log_file="${LOGS_DIR}/sample_${sample_index}.log"
        
        log_info "Starting sample $sample_index ($(($sample_idx + 1))/$TOTAL_SAMPLES) - Running: $(get_running_count)/$N_CONCURRENT"
        
        # Start the job in background with force-build if requested
        run_harbor_sample "$sample_index" "$EXPERIMENT_NAME" "$MODEL" "$MAX_QUESTIONS" "$FORCE_BUILD" "$EXTRA_ARGS" "$log_file" &
        pid=$!
        
        PIDS+=("$pid")
        SAMPLES_RUNNING+=("$sample_index")
        SAMPLE_START_TIMES+=("$(date +%s)")
        
        ((sample_idx++))
        
        # Add delay between starting containers to avoid Docker conflicts
        if [ $sample_idx -lt $TOTAL_SAMPLES ] && [ "$(get_running_count)" -lt "$N_CONCURRENT" ]; then
            sleep $START_DELAY_SECONDS
        fi
    done
    
    # Show periodic status update
    current_time=$(date +%s)
    if [ $((current_time - last_status_time)) -ge $STATUS_INTERVAL ] && [ "$(get_running_count)" -gt 0 ]; then
        display_status
        last_status_time=$current_time
    fi
    
    # If we have running jobs, wait a bit before checking again
    if [ "$(get_running_count)" -gt 0 ]; then
        sleep 5
    fi
done

# =============================================================================
# Summary
# =============================================================================

TOTAL_TIME=$(get_elapsed_time)

echo ""
log_info "=========================================="
log_info "Execution Summary"
log_info "=========================================="
log_info "Total Execution Time: $TOTAL_TIME"
log_info "Experiment Name: $EXPERIMENT_NAME"
log_info "Total Samples: $TOTAL_SAMPLES"
log_success "Completed: $completed_count"

if [ $failed_count -gt 0 ]; then
    log_error "Failed: $failed_count"
    echo ""
    log_error "Failed samples:"
    for sample in "${FAILED_SAMPLES[@]}"; do
        echo "  - sample_$sample (see ${LOGS_DIR}/sample_${sample}.log)"
    done
fi

echo ""
log_info "Completed samples: ${COMPLETED_SAMPLES[*]}"
log_info "Logs saved to: $LOGS_DIR"
log_info "=========================================="

# Exit with error if any samples failed
if [ $failed_count -gt 0 ]; then
    exit 1
fi

exit 0
