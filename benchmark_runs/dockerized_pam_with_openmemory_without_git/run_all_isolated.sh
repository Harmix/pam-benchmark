#!/bin/bash

# Run all configs with full container isolation
# Each config gets a fresh container instance

CONFIG_DIR="./test_configs"
OUTPUT_DIR="./outputs"

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "Error: docker-compose not found. Please install docker-compose."
    exit 1
fi

mkdir -p "$OUTPUT_DIR"

# Get all config files sorted
CONFIG_FILES=($(ls "$CONFIG_DIR"/*.yaml 2>/dev/null | sort))

if [ ${#CONFIG_FILES[@]} -eq 0 ]; then
    echo "Error: No config files found in $CONFIG_DIR"
    exit 1
fi

TOTAL_CONFIGS=${#CONFIG_FILES[@]}
BATCH_TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Create batch run directory
BATCH_DIR="$OUTPUT_DIR/batch_run_${BATCH_TIMESTAMP}"
mkdir -p "$BATCH_DIR"

echo "========================================"
echo "Isolated Batch Benchmark Runner"
echo "========================================"
echo "Found $TOTAL_CONFIGS configuration files"
echo "Each config runs in a fresh container"
echo "Batch directory: $BATCH_DIR"
echo ""

BATCH_SUMMARY="$BATCH_DIR/batch_summary.txt"

echo "Isolated Batch Benchmark Run" > "$BATCH_SUMMARY"
echo "============================" >> "$BATCH_SUMMARY"
echo "Start Time: $(date)" >> "$BATCH_SUMMARY"
echo "Total Configs: $TOTAL_CONFIGS" >> "$BATCH_SUMMARY"
echo "Batch Directory: $BATCH_DIR" >> "$BATCH_SUMMARY"
echo "" >> "$BATCH_SUMMARY"

SUCCESSFUL=0
FAILED=0

for i in "${!CONFIG_FILES[@]}"; do
    CONFIG_FILE="${CONFIG_FILES[$i]}"
    CONFIG_NAME=$(basename "$CONFIG_FILE" .yaml)
    CONFIG_NUM=$((i + 1))

    echo ""
    echo "========================================"
    echo "Config $CONFIG_NUM/$TOTAL_CONFIGS: $CONFIG_NAME"
    echo "========================================"
    echo "Started: $(date)"
    echo "Starting fresh container..."

    START_TIME=$(date +%s)

    # Container log will be saved in batch directory
    CONTAINER_LOG="$BATCH_DIR/${CONFIG_NAME}_container.log"

    # Run in fresh container - automatically removed after completion
    # The --rm flag ensures complete cleanup
    if docker-compose run --rm claude-code /benchmark_data/setup_and_run.sh "/benchmark_data/test_configs/${CONFIG_NAME}.yaml" 2>&1 | tee "$CONTAINER_LOG"; then
        STATUS="SUCCESS"
        ((SUCCESSFUL++))
    else
        STATUS="FAILED"
        ((FAILED++))
    fi

    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))

    echo ""
    echo "Config $CONFIG_NUM completed: $STATUS"
    echo "Duration: ${DURATION}s ($(($DURATION / 60))m $(($DURATION % 60))s)"
    echo "Completed: $(date)"

    # Log to summary
    echo "Config $CONFIG_NUM: $CONFIG_NAME" >> "$BATCH_SUMMARY"
    echo "  Status: $STATUS" >> "$BATCH_SUMMARY"
    echo "  Duration: ${DURATION}s ($(($DURATION / 60))m $(($DURATION % 60))s)" >> "$BATCH_SUMMARY"
    echo "  Container Log: ${CONFIG_NAME}_container.log" >> "$BATCH_SUMMARY"
    echo "  Config Logs: Check outputs/ for ${CONFIG_NAME}_* directories" >> "$BATCH_SUMMARY"
    echo "  Started: $(date -d "@$START_TIME" 2>/dev/null || date -r $START_TIME 2>/dev/null || date)" >> "$BATCH_SUMMARY"
    echo "  Completed: $(date -d "@$END_TIME" 2>/dev/null || date -r $END_TIME 2>/dev/null || date)" >> "$BATCH_SUMMARY"
    echo "" >> "$BATCH_SUMMARY"

    echo "Container cleaned up. Ready for next config."

    # Small delay between runs
    if [ $CONFIG_NUM -lt $TOTAL_CONFIGS ]; then
        echo "Waiting 5 seconds before next config..."
        sleep 5
    fi
done

BATCH_END_TIME=$(date +%s)

echo ""
echo "========================================"
echo "Isolated Batch Run Complete"
echo "========================================"
echo "Total Configs: $TOTAL_CONFIGS"
echo "Successful: $SUCCESSFUL"
echo "Failed: $FAILED"
echo "Batch Directory: $BATCH_DIR"
echo "Results saved to: $OUTPUT_DIR"
echo ""

# Add final summary to file
echo "=======================================" >> "$BATCH_SUMMARY"
echo "Final Summary" >> "$BATCH_SUMMARY"
echo "=======================================" >> "$BATCH_SUMMARY"
echo "End Time: $(date)" >> "$BATCH_SUMMARY"
echo "Total Configs: $TOTAL_CONFIGS" >> "$BATCH_SUMMARY"
echo "Successful: $SUCCESSFUL" >> "$BATCH_SUMMARY"
echo "Failed: $FAILED" >> "$BATCH_SUMMARY"
if [ $TOTAL_CONFIGS -gt 0 ]; then
    SUCCESS_RATE=$(echo "scale=1; ($SUCCESSFUL * 100) / $TOTAL_CONFIGS" | bc)
    echo "Success Rate: ${SUCCESS_RATE}%" >> "$BATCH_SUMMARY"
fi
echo "" >> "$BATCH_SUMMARY"
echo "Log Structure:" >> "$BATCH_SUMMARY"
echo "==============" >> "$BATCH_SUMMARY"
echo "- batch_summary.txt: This file" >> "$BATCH_SUMMARY"
echo "- <config_name>_container.log: Container execution log for each config" >> "$BATCH_SUMMARY"
echo "- ../: Parent directory contains individual config result directories" >> "$BATCH_SUMMARY"
echo "  - <config_name>_<timestamp>/" >> "$BATCH_SUMMARY"
echo "    - summary.txt: Config-specific summary" >> "$BATCH_SUMMARY"
echo "    - questions/: Question logs" >> "$BATCH_SUMMARY"
echo "      - question_0.log" >> "$BATCH_SUMMARY"
echo "      - question_1.log" >> "$BATCH_SUMMARY"
echo "      - ..." >> "$BATCH_SUMMARY"

echo "Batch summary saved to: $BATCH_SUMMARY"

exit 0