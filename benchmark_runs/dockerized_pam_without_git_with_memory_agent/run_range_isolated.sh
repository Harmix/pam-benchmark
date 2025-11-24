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

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "Error: docker-compose not found. Please install docker-compose."
    exit 1
fi

mkdir -p "$OUTPUT_DIR"

BATCH_TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BATCH_DIR="$OUTPUT_DIR/batch_range_${START}_to_${END}_${BATCH_TIMESTAMP}"
mkdir -p "$BATCH_DIR"

BATCH_SUMMARY="$BATCH_DIR/batch_summary.txt"

echo "========================================"
echo "Running configs $START to $END (isolated)"
echo "========================================"
echo "Each config gets fresh environment"
echo "Batch directory: $BATCH_DIR"
echo ""

echo "Batch Range Run: Config $START to $END" > "$BATCH_SUMMARY"
echo "Start Time: $(date)" >> "$BATCH_SUMMARY"
echo "Mode: No MCP/Git - Direct file processing" >> "$BATCH_SUMMARY"
echo "" >> "$BATCH_SUMMARY"

SUCCESSFUL=0
FAILED=0
SKIPPED=0
TOTAL=$((END - START + 1))

for i in $(seq $START $END); do
    CONFIG_NAME="config_${i}"
    CONFIG_FILE="${CONFIG_DIR}/${CONFIG_NAME}.yaml"

    if [ ! -f "$CONFIG_FILE" ]; then
        echo "Skipping: $CONFIG_NAME (file not found)"
        echo "$CONFIG_NAME: SKIPPED (file not found)" >> "$BATCH_SUMMARY"
        ((SKIPPED++))
        continue
    fi

    echo ""
    echo "========================================"
    echo "Running: $CONFIG_NAME (${i}/${END})"
    echo "========================================"
    echo "Started: $(date)"

    START_TIME=$(date +%s)
    CONTAINER_LOG="$BATCH_DIR/${CONFIG_NAME}_container.log"

    # Run with fresh container - automatically removed after completion
    echo "Starting fresh container for $CONFIG_NAME..."

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
    echo "Config $CONFIG_NAME: $STATUS"
    echo "Duration: ${DURATION}s ($(($DURATION / 60))m $(($DURATION % 60))s)"
    echo "Completed: $(date)"

    # Log to summary
    echo "$CONFIG_NAME: $STATUS (${DURATION}s)" >> "$BATCH_SUMMARY"
    echo "  Container log: ${CONFIG_NAME}_container.log" >> "$BATCH_SUMMARY"
    echo "  Result logs: Check outputs/ for ${CONFIG_NAME}_* directories" >> "$BATCH_SUMMARY"
    echo "" >> "$BATCH_SUMMARY"

    # Small delay between configs
    if [ $i -lt $END ]; then
        echo "Waiting 5 seconds before next config..."
        sleep 5
    fi
done

echo ""
echo "========================================"
echo "Batch Run Complete"
echo "========================================"
echo "Total Configs: $TOTAL"
echo "Successful: $SUCCESSFUL"
echo "Failed: $FAILED"
echo "Skipped: $SKIPPED"
echo "Batch Directory: $BATCH_DIR"

# Add final summary
echo "" >> "$BATCH_SUMMARY"
echo "=======================================" >> "$BATCH_SUMMARY"
echo "Final Summary" >> "$BATCH_SUMMARY"
echo "=======================================" >> "$BATCH_SUMMARY"
echo "End Time: $(date)" >> "$BATCH_SUMMARY"
echo "Total Configs: $TOTAL" >> "$BATCH_SUMMARY"
echo "Successful: $SUCCESSFUL" >> "$BATCH_SUMMARY"
echo "Failed: $FAILED" >> "$BATCH_SUMMARY"
echo "Skipped: $SKIPPED" >> "$BATCH_SUMMARY"

if [ $((SUCCESSFUL + FAILED)) -gt 0 ]; then
    SUCCESS_RATE=$(echo "scale=1; ($SUCCESSFUL * 100) / ($SUCCESSFUL + $FAILED)" | bc 2>/dev/null || echo "N/A")
    echo "Success Rate: ${SUCCESS_RATE}%" >> "$BATCH_SUMMARY"
fi

echo "" >> "$BATCH_SUMMARY"
echo "Log Files:" >> "$BATCH_SUMMARY"
echo "- Each config has a container log: <config_name>_container.log" >> "$BATCH_SUMMARY"
echo "- Each config creates a result directory in outputs/" >> "$BATCH_SUMMARY"
echo "  Format: <config_name>_<timestamp>/" >> "$BATCH_SUMMARY"
echo "    ├── summary.txt" >> "$BATCH_SUMMARY"
echo "    └── questions/" >> "$BATCH_SUMMARY"
echo "        └── question_N.log" >> "$BATCH_SUMMARY"

echo ""
echo "Batch summary saved to: $BATCH_SUMMARY"

exit 0