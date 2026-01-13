#!/bin/bash
# Helper script to prepare the benchmark directory for Docker build
# This copies the dataset into the benchmark directory so it's available in the build context

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Script is in benchmark/, so project root is one level up
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DATASET_SOURCE="$PROJECT_ROOT/datasets/memtrack"
# Copy dataset to benchmark/environment/ so it's available in Docker build context
DATASET_DEST="$SCRIPT_DIR/environment/datasets/memtrack"

echo "Preparing dataset for Docker build..."
echo "Source: $DATASET_SOURCE"
echo "Dest: $DATASET_DEST"

if [ ! -d "$DATASET_SOURCE" ]; then
    echo "Error: Dataset source not found at $DATASET_SOURCE"
    exit 1
fi

# Remove existing symlink or directory
if [ -L "$DATASET_DEST" ] || [ -d "$DATASET_DEST" ]; then
    rm -rf "$DATASET_DEST"
fi

# Copy dataset into benchmark directory
mkdir -p "$(dirname "$DATASET_DEST")"
cp -r "$DATASET_SOURCE" "$DATASET_DEST"

echo "Dataset prepared successfully!"
