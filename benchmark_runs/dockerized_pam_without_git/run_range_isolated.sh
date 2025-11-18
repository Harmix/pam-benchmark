#!/bin/bash

# Run a range of configs with isolation
# Usage: ./run_range_isolated.sh 1 10

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

echo "========================================"
echo "Running configs $START to $END (isolated)"
echo "========================================"
echo "Batch directory: $BATCH_DIR"
echo "" | tee "$BATCH_SUMMARY"

echo "Batch Range Run: Config $START to $END" >> "$BATCH_SUMMARY"
echo "Start Time: $(date)" >> "$BATCH_SUMMARY"
echo "" >> "$BATCH_SUMMARY"

SUCCESSFUL=0
FAILED=0
TOTAL=$((END - START + 1))

for i in $(seq $START $END); do
    CONFIG_NAME="config_${i}"
    CONFIG_FILE="${CONFIG_DIR}/${CONFIG_NAME}.yaml"

    if [ ! -f "$CONFIG_FILE" ]; then
        echo "Skipping: $CONFIG_NAME (file not found)" | tee -a "$BATCH_SUMMARY"
        continue
    fi

    echo ""
    echo "========================================"
    echo "Running: $CONFIG_NAME ($i/$END)"
    echo "========================================"

    START_TIME=$(date +%s)
    CONTAINER_LOG="$BATCH_DIR/${CONFIG_NAME}_container.log"

    if docker-compose run --rm claude-code /benchmark_data/setup_and_run.sh "/benchmark_data/test_configs/${CONFIG_NAME}.yaml" 2>&1 | tee "$CONTAINER_LOG"; then
        STATUS="SUCCESS"
        ((SUCCESSFUL++))
    else
        STATUS="FAILED"
        ((FAILED++))
    fi

    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))

    echo "$CONFIG_NAME: $STATUS (${DURATION}s)" | tee -a "$BATCH_SUMMARY"

    sleep 5
done

echo "" | tee -a "$BATCH_SUMMARY"
echo "Summary: $SUCCESSFUL/$TOTAL successful, $((TOTAL - SUCCESSFUL)) failed" | tee -a "$BATCH_SUMMARY"
echo "Batch directory: $BATCH_DIR" | tee -a "$BATCH_SUMMARY"