#!/bin/bash

# Harbor test script for PAM Benchmark Task
# This script verifies that the task was completed successfully

set -e

echo "=========================================="
echo "PAM Benchmark Task Verification"
echo "=========================================="

# Install dependencies for testing
apt-get update
apt-get install -y curl

# Install uv for Python package management
curl -LsSf https://astral.sh/uv/0.9.5/install.sh | sh
source $HOME/.local/bin/env

# Run pytest tests
uvx \
  --python 3.12 \
  --with pytest==8.4.1 \
  pytest /tests/test_outputs.py

# Check exit code and write reward
if [ $? -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
  echo "✓ Task verification passed"
else
  echo 0 > /logs/verifier/reward.txt
  echo "✗ Task verification failed"
  exit 1
fi

