#!/bin/bash

# Harbor test script for LoCoMo Benchmark Task
# This script verifies that the task was completed successfully

echo "=========================================="
echo "LoCoMo Task Verification"
echo "=========================================="

# Check if output files exist
OUTPUT_FILE="/outputs/locomo10_qa.json"
STATS_FILE="/outputs/locomo10_qa_stats.json"

# For PAM model, check task_logs for answers
PAM_ANSWERS=$(find /task_logs -name "pam_answers.json" 2>/dev/null | head -1)
PAM_METRICS=$(find /task_logs -name "metrics.json" 2>/dev/null | head -1)

echo "Checking output files..."

PASSED=true

# Check for standard model outputs OR PAM outputs
if [ -f "$OUTPUT_FILE" ]; then
    echo "✓ Found output file: $OUTPUT_FILE"
    # Check if file has content
    if [ -s "$OUTPUT_FILE" ]; then
        echo "✓ Output file has content"
    else
        echo "✗ Output file is empty"
        PASSED=false
    fi
elif [ -n "$PAM_ANSWERS" ] && [ -f "$PAM_ANSWERS" ]; then
    echo "✓ Found PAM answers file: $PAM_ANSWERS"
    if [ -s "$PAM_ANSWERS" ]; then
        echo "✓ PAM answers file has content"
    else
        echo "✗ PAM answers file is empty"
        PASSED=false
    fi
else
    echo "✗ No output file found (neither $OUTPUT_FILE nor PAM answers)"
    PASSED=false
fi

# Check for stats/metrics
if [ -f "$STATS_FILE" ]; then
    echo "✓ Found stats file: $STATS_FILE"
elif [ -n "$PAM_METRICS" ] && [ -f "$PAM_METRICS" ]; then
    echo "✓ Found PAM metrics file: $PAM_METRICS"
else
    echo "⚠ No stats/metrics file found (optional)"
fi

# Write reward based on verification result
echo ""
echo "=========================================="
if [ "$PASSED" = true ]; then
    echo "✓ Task verification PASSED"
    echo 1 > /logs/verifier/reward.txt
    exit 0
else
    echo "✗ Task verification FAILED"
    echo 0 > /logs/verifier/reward.txt
    exit 1
fi
