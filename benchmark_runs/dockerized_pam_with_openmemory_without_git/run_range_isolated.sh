##!/bin/bash
#
## Run a range of configs with isolation
## Usage: ./run_range_isolated.sh 1 10
#
#if [ $# -ne 2 ]; then
#    echo "Usage: $0 <start_number> <end_number>"
#    echo "Example: $0 1 10"
#    exit 1
#fi
#
#START=$1
#END=$2
#CONFIG_DIR="./test_configs"
#OUTPUT_DIR="./outputs"
#
#mkdir -p "$OUTPUT_DIR"
#
#BATCH_TIMESTAMP=$(date +%Y%m%d_%H%M%S)
#BATCH_DIR="$OUTPUT_DIR/batch_range_${START}_to_${END}_${BATCH_TIMESTAMP}"
#mkdir -p "$BATCH_DIR"
#
#BATCH_SUMMARY="$BATCH_DIR/batch_summary.txt"
#
#echo "========================================"
#echo "Running configs $START to $END (isolated)"
#echo "========================================"
#echo "Batch directory: $BATCH_DIR"
#echo "" | tee "$BATCH_SUMMARY"
#
#echo "Batch Range Run: Config $START to $END" >> "$BATCH_SUMMARY"
#echo "Start Time: $(date)" >> "$BATCH_SUMMARY"
#echo "" >> "$BATCH_SUMMARY"
#
#SUCCESSFUL=0
#FAILED=0
#TOTAL=$((END - START + 1))
#
#for i in $(seq $START $END); do
#    CONFIG_NAME="config_${i}"
#    CONFIG_FILE="${CONFIG_DIR}/${CONFIG_NAME}.yaml"
#
#    if [ ! -f "$CONFIG_FILE" ]; then
#        echo "Skipping: $CONFIG_NAME (file not found)" | tee -a "$BATCH_SUMMARY"
#        continue
#    fi
#
#    echo ""
#    echo "========================================"
#    echo "Running: $CONFIG_NAME ($i/$END)"
#    echo "========================================"
#
#    START_TIME=$(date +%s)
#    CONTAINER_LOG="$BATCH_DIR/${CONFIG_NAME}_container.log"
#
#    if docker-compose run --rm claude-code /benchmark_data/setup_and_run.sh "/benchmark_data/test_configs/${CONFIG_NAME}.yaml" 2>&1 | tee "$CONTAINER_LOG"; then
#        STATUS="SUCCESS"
#        ((SUCCESSFUL++))
#    else
#        STATUS="FAILED"
#        ((FAILED++))
#    fi
#
#    END_TIME=$(date +%s)
#    DURATION=$((END_TIME - START_TIME))
#
#    echo "$CONFIG_NAME: $STATUS (${DURATION}s)" | tee -a "$BATCH_SUMMARY"
#
#    sleep 5
#done
#
#echo "" | tee -a "$BATCH_SUMMARY"
#echo "Summary: $SUCCESSFUL/$TOTAL successful, $((TOTAL - SUCCESSFUL)) failed" | tee -a "$BATCH_SUMMARY"
#echo "Batch directory: $BATCH_DIR" | tee -a "$BATCH_SUMMARY"

#!/bin/bash

# Run a range of configs with isolation and OpenMemory management
# Usage: ./run_range_isolated.sh 1 10

#!/bin/bash

# Run a range of configs with isolation and OpenMemory management
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

# Check if container exists (running or stopped)
if docker ps -a --format '{{.Names}}' | grep -q '^claude-code$'; then
    # Container exists - check if it's running
    if docker ps --format '{{.Names}}' | grep -q '^claude-code$'; then
        echo "Container already running"
    else
        echo "Container exists but stopped - starting..."
        docker start claude-code
        sleep 5
    fi
else
    # Container doesn't exist - create and start it
    echo "Creating and starting container..."
    docker-compose up -d
    sleep 10
fi

# Verify container is actually running
if ! docker ps --format '{{.Names}}' | grep -q '^claude-code$'; then
    echo "ERROR: Failed to start container"
    exit 1
fi

echo "Container ready"
echo ""

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

    # Run benchmark inside persistent container with OpenMemory management
    if docker exec claude-code bash -c "
        # Stop any previous OpenMemory instance to free resources
        /usr/local/bin/openmemory_setup.sh stop 2>/dev/null || true

        # Small delay to ensure clean shutdown
        sleep 2

        # Run the benchmark (setup_and_run.sh will start OpenMemory)
        /benchmark_data/setup_and_run.sh /benchmark_data/test_configs/${CONFIG_NAME}.yaml

        # Stop OpenMemory after config completes to free resources for next run
        /usr/local/bin/openmemory_setup.sh stop
    " 2>&1 | tee "$CONTAINER_LOG"; then
        STATUS="SUCCESS"
        ((SUCCESSFUL++))
    else
        STATUS="FAILED"
        ((FAILED++))

        # On failure, ensure OpenMemory is stopped for next run
        docker exec claude-code /usr/local/bin/openmemory_setup.sh stop 2>/dev/null || true
    fi

    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))

    echo "$CONFIG_NAME: $STATUS (${DURATION}s)" | tee -a "$BATCH_SUMMARY"

    # Brief pause between configs
    sleep 3
done

echo "" | tee -a "$BATCH_SUMMARY"
echo "========================================"
echo "Batch Run Complete"
echo "========================================"
echo "End Time: $(date)" | tee -a "$BATCH_SUMMARY"
echo "" | tee -a "$BATCH_SUMMARY"
echo "Results:" | tee -a "$BATCH_SUMMARY"
echo "  Successful: $SUCCESSFUL/$TOTAL" | tee -a "$BATCH_SUMMARY"
echo "  Failed: $FAILED/$TOTAL" | tee -a "$BATCH_SUMMARY"
echo "" | tee -a "$BATCH_SUMMARY"
echo "Batch directory: $BATCH_DIR" | tee -a "$BATCH_SUMMARY"
echo "Individual run outputs: $OUTPUT_DIR/config_*/" | tee -a "$BATCH_SUMMARY"
echo ""

# Show memory usage summary
echo "Memory Storage Summary:" | tee -a "$BATCH_SUMMARY"
if docker exec claude-code bash -c "[ -d /openmemory/memories ] && du -sh /openmemory/memories/* 2>/dev/null" | tee -a "$BATCH_SUMMARY"; then
    :
else
    echo "  No memories stored yet" | tee -a "$BATCH_SUMMARY"
fi

echo ""
echo "View logs: cat $BATCH_DIR/<config>_container.log"
echo "View summary: cat $BATCH_SUMMARY"