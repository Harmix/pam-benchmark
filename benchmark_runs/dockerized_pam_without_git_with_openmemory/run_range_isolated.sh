#!/bin/bash
set -e

if [ $# -ne 2 ]; then
    echo "Usage: $0 <start_number> <end_number>"
    echo "Example: $0 1 10"
    exit 1
fi

START=$1
END=$2
CONFIG_DIR="./test_configs"
OUTPUT_DIR="./outputs"

mkdir -p "$OUTPUT_DIR"

BATCH_TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BATCH_DIR="$OUTPUT_DIR/batch_range_${START}_to_${END}_${BATCH_TIMESTAMP}"
mkdir -p "$BATCH_DIR"

BATCH_SUMMARY="$BATCH_DIR/batch_summary.txt"

# Get all config files sorted
ALL_CONFIGS=($(ls "$CONFIG_DIR"/*.yaml 2>/dev/null | sort))

if [ ${#ALL_CONFIGS[@]} -eq 0 ]; then
    echo "Error: No config files found in $CONFIG_DIR"
    exit 1
fi

# Validate range
if [ $START -lt 1 ] || [ $END -gt ${#ALL_CONFIGS[@]} ]; then
    echo "Error: Range $START-$END is invalid. Available configs: 1-${#ALL_CONFIGS[@]}"
    exit 1
fi

echo "========================================"
echo "Running configs $START to $END"
echo "========================================"
echo "Total available configs: ${#ALL_CONFIGS[@]}"
echo "Batch directory: $BATCH_DIR"
echo ""

# Setup OpenMemory if not already done
if [ ! -d "mem0" ]; then
    echo "Setting up OpenMemory for the first time..."
    ./setup_openmemory.sh
fi

# Start services once for all benchmarks
echo "Starting OpenMemory services..."
docker-compose up -d mem0_store openmemory-api

# Simple wait for services to be ready
echo "Waiting for services to initialize..."
sleep 30

# Verify services are running
echo "Checking service status..."
if ! docker-compose ps | grep -q "mem0_store.*Up"; then
    echo "ERROR: Qdrant is not running"
    docker-compose logs mem0_store
    exit 1
fi

if ! docker-compose ps | grep -q "openmemory-api.*Up"; then
    echo "ERROR: OpenMemory API is not running"
    docker-compose logs openmemory-api
    exit 1
fi

echo "All services running!"
echo ""

# Initialize batch summary
echo "Batch Range Run: Config $START to $END (of ${#ALL_CONFIGS[@]})" | tee "$BATCH_SUMMARY"
echo "Start Time: $(date)" | tee -a "$BATCH_SUMMARY"
echo "OpenMemory Services: Running" | tee -a "$BATCH_SUMMARY"
echo "" | tee -a "$BATCH_SUMMARY"

SUCCESSFUL=0
FAILED=0
TOTAL=$((END - START + 1))
FAILED_CONFIGS=""

# Array indices are 0-based, so subtract 1
for i in $(seq $((START - 1)) $((END - 1))); do
    CONFIG_FILE="${ALL_CONFIGS[$i]}"
    CONFIG_NAME=$(basename "$CONFIG_FILE" .yaml)
    CONFIG_NUM=$((i + 1))

    echo ""
    echo "========================================"
    echo "Running: $CONFIG_NAME ($CONFIG_NUM/$END)"
    echo "========================================"

    START_TIME=$(date +%s)
    CONTAINER_LOG="$BATCH_DIR/${CONFIG_NAME}_container.log"

    # Run the benchmark
    set +e
    docker-compose run --rm claude-code /benchmark_data/setup_and_run.sh "/benchmark_data/test_configs/${CONFIG_NAME}.yaml" 2>&1 | tee "$CONTAINER_LOG"
    EXIT_CODE=$?
    set -e

    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    DURATION_MIN=$((DURATION / 60))
    DURATION_SEC=$((DURATION % 60))

    if [ $EXIT_CODE -eq 0 ]; then
        STATUS="✓ SUCCESS"
        ((SUCCESSFUL++))
        echo "$CONFIG_NAME: $STATUS (${DURATION_MIN}m ${DURATION_SEC}s)" | tee -a "$BATCH_SUMMARY"
    else
        STATUS="✗ FAILED"
        ((FAILED++))
        FAILED_CONFIGS="${FAILED_CONFIGS}${CONFIG_NAME} (exit code: $EXIT_CODE)\n"
        echo "$CONFIG_NAME: $STATUS (${DURATION_MIN}m ${DURATION_SEC}s) - Exit code: $EXIT_CODE" | tee -a "$BATCH_SUMMARY"
    fi

    # Brief pause between runs
    if [ $CONFIG_NUM -lt $END ]; then
        echo "Waiting 5 seconds before next config..."
        sleep 5
    fi
done

# Final summary
echo "" | tee -a "$BATCH_SUMMARY"
echo "========================================"  | tee -a "$BATCH_SUMMARY"
echo "BATCH COMPLETE" | tee -a "$BATCH_SUMMARY"
echo "========================================" | tee -a "$BATCH_SUMMARY"
echo "End Time: $(date)" | tee -a "$BATCH_SUMMARY"
echo "" | tee -a "$BATCH_SUMMARY"
echo "Results: $SUCCESSFUL/$TOTAL successful, $FAILED failed" | tee -a "$BATCH_SUMMARY"
echo "" | tee -a "$BATCH_SUMMARY"

if [ $FAILED -gt 0 ]; then
    echo "Failed Configs:" | tee -a "$BATCH_SUMMARY"
    echo -e "$FAILED_CONFIGS" | tee -a "$BATCH_SUMMARY"
fi

echo "Batch directory: $BATCH_DIR" | tee -a "$BATCH_SUMMARY"
echo "Container logs: $BATCH_DIR/*_container.log" | tee -a "$BATCH_SUMMARY"
echo "" | tee -a "$BATCH_SUMMARY"

# Check if services are still running
if docker-compose ps | grep -q "openmemory-api.*Up"; then
    echo "OpenMemory API: Still running" | tee -a "$BATCH_SUMMARY"
else
    echo "WARNING: OpenMemory API stopped" | tee -a "$BATCH_SUMMARY"
fi

if docker-compose ps | grep -q "mem0_store.*Up"; then
    echo "Qdrant: Still running" | tee -a "$BATCH_SUMMARY"
else
    echo "WARNING: Qdrant stopped" | tee -a "$BATCH_SUMMARY"
fi

echo ""
echo "========================================"
echo "Stopping services..."
echo "========================================"
docker-compose down

echo ""
echo "Batch complete! Check results in: $BATCH_DIR"