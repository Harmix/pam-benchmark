#!/bin/bash

echo "=========================================="
echo "LongMemEval Task Verification"
echo "=========================================="

PREDICTIONS_FILE="/outputs/longmemeval_predictions.jsonl"
EVAL_FILE="/outputs/longmemeval_eval_results.jsonl"
STATS_FILE="/outputs/longmemeval_stats.json"

echo "Checking output files..."

PASSED=true

if [ -f "$PREDICTIONS_FILE" ]; then
    echo "✓ Found predictions file: $PREDICTIONS_FILE"
    if [ -s "$PREDICTIONS_FILE" ]; then
        LINE_COUNT=$(wc -l < "$PREDICTIONS_FILE")
        echo "✓ Predictions file has ${LINE_COUNT} entries"
    else
        echo "✗ Predictions file is empty"
        PASSED=false
    fi
else
    echo "✗ No predictions file found at $PREDICTIONS_FILE"
    PASSED=false
fi

if [ -f "$EVAL_FILE" ]; then
    echo "✓ Found evaluation file: $EVAL_FILE"
elif [ -f "$STATS_FILE" ]; then
    echo "✓ Found stats file: $STATS_FILE"
else
    echo "⚠ No evaluation/stats files found (optional)"
fi

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
