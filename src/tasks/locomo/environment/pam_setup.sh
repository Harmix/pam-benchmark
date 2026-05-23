#!/bin/bash
# PAM Setup Script for LoCoMo
# Phase 1: Setup workspace and create PAM folder structure

set -e

SAMPLE_ID="${1:-sample_0}"
DATA_FILE="${2:-/task_data/data/locomo10.json}"
SAMPLE_INDEX="${3:-0}"

echo "========================================"
echo "PAM Setup: $SAMPLE_ID"
echo "========================================"
echo ""

# Clean up workspace
echo "Cleaning workspace..."
rm -rf /workspace/unsorted
rm -rf /workspace/*.md
rm -rf /workspace/*.py
rm -rf /workspace/*_context/
mkdir -p /workspace/unsorted
echo "Workspace cleaned"
echo ""

# Copy PAM guide files to workspace
echo "Copying PAM guide files to workspace..."
cp /task_data/INIT.md /workspace/INIT.md
cp /task_data/init.py /workspace/init.py
cp /task_data/INTRO_TEMPLATE.md /workspace/INTRO_TEMPLATE.md

if [ -f "/task_data/CLAUDE.md" ]; then
    cp /task_data/CLAUDE.md /workspace/CLAUDE.md
    echo "CLAUDE.md copied"
fi
echo "PAM guide files copied to /workspace/"
echo ""

# Extract conversation data using pam_utils.py
echo "Extracting conversation data..."
python3 /task_data/pam_utils.py extract \
    --data-file "$DATA_FILE" \
    --sample-index "$SAMPLE_INDEX" \
    --output-dir /workspace/unsorted

echo ""

# Extract questions
echo "Extracting questions..."
python3 /task_data/pam_utils.py questions \
    --data-file "$DATA_FILE" \
    --sample-index "$SAMPLE_INDEX" \
    --questions-file /workspace/questions.json

echo ""

# Run init.py to create PAM folder structure
echo "Creating PAM Memory Folder Structure..."
cd /workspace
python3 init.py "${SAMPLE_ID}_context" 2>&1 | head -20

# Fix permissions
chmod -R 777 /workspace/${SAMPLE_ID}_context_context/ 2>/dev/null || true
chmod 777 /workspace/unsorted/

echo ""
echo "PAM folder structure created at: /workspace/${SAMPLE_ID}_context_context/"
ls -la /workspace/*_context/ 2>/dev/null | head -10
echo ""

echo "========================================"
echo "PAM Setup Complete"
echo "========================================"
