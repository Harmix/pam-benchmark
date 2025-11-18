#!/bin/bash

# Run all configs with full container isolation
# Each config gets a fresh container instance
# OpenMemory services stay running for all configs

set -e

CONFIG_DIR="./test_configs"
OUTPUT_DIR="./outputs"

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "Error: docker-compose not found. Please install docker-compose."
    exit 1
fi

mkdir -p "$OUTPUT_DIR"

# Get all config files sorted
CONFIG_FILES=($(ls "$CONFIG_DIR"/*.yaml 2>/dev/null | sort -V))

if [ ${#CONFIG_FILES[@]} -eq 0 ]; then
    echo "Error: No config files found in $CONFIG_DIR"
    exit 1
fi

TOTAL_CONFIGS=${#CONFIG_FILES[@]}
BATCH_TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Create batch run directory
BATCH_DIR="$OUTPUT_DIR/batch_all_${BATCH_TIMESTAMP}"
mkdir -p "$BATCH_DIR"

BATCH_SUMMARY="$BATCH_DIR/batch_summary.txt"

echo "========================================"
echo "Running all configs"
echo "========================================"
echo "Found $TOTAL_CONFIGS configuration files"
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
echo "Batch All Run: All Configs" | tee "$BATCH_SUMMARY"
echo "Start Time: $(date)" | tee -a "$BATCH_SUMMARY"
echo "Total Configs: $TOTAL_CONFIGS" | tee -a "$BATCH_SUMMARY"
echo "OpenMemory Services: Running" | tee -a "$BATCH_SUMMARY"
echo "" | tee -a "$BATCH_SUMMARY"

SUCCESSFUL=0
FAILED=0
FAILED_CONFIGS=""

for i in "${!CONFIG_FILES[@]}"; do
    CONFIG_FILE="${CONFIG_FILES[$i]}"
    CONFIG_NAME=$(basename "$CONFIG_FILE" .yaml)
    CONFIG_NUM=$((i + 1))

    echo ""
    echo "========================================"
    echo "Running: $CONFIG_NAME ($CONFIG_NUM/$TOTAL_CONFIGS)"
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
    if [ $CONFIG_NUM -lt $TOTAL_CONFIGS ]; then
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
echo "Results: $SUCCESSFUL/$TOTAL_CONFIGS successful, $FAILED failed" | tee -a "$BATCH_SUMMARY"
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