#!/bin/bash

CONFIG_FILE="${1:-/benchmark_data/test_configs/config_1.yaml}"

# Extract config name from path
CONFIG_NAME=$(basename "$CONFIG_FILE" .yaml)
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Create organized directory structure
CONFIG_LOG_DIR="/workspace/logs/${CONFIG_NAME}_${TIMESTAMP}"
QUESTIONS_DIR="$CONFIG_LOG_DIR/questions"
mkdir -p "$QUESTIONS_DIR"

echo "========================================"
echo "Starting Benchmark: $CONFIG_NAME"
echo "========================================"
echo "Reading configuration from: $CONFIG_FILE"
echo "Logs directory: $CONFIG_LOG_DIR"
echo ""

# Parse YAML using yq
REPO_URL=$(yq eval '.repository.url' "$CONFIG_FILE")
REPO_NAME=$(yq eval '.repository.local_name' "$CONFIG_FILE")
EVENT_HISTORY=$(yq eval '.benchmark.event_history' "$CONFIG_FILE")
EVENT_HISTORY_PATH="/benchmark_data/$EVENT_HISTORY"

echo "Repository URL: $REPO_URL"
echo "Repository Name: $REPO_NAME"
echo "Event History: $EVENT_HISTORY_PATH"
echo ""

## Clone repository
#if [ ! -d "/workspace/$REPO_NAME" ]; then
#    echo "Cloning repository..."
#    cd /workspace
#    if ! git clone "$REPO_URL" "$REPO_NAME"; then
#        echo "ERROR: Clone failed. Please check repository URL and GITHUB_TOKEN."
#        exit 1
#    fi
#else
#    echo "Repository already exists at /workspace/$REPO_NAME. Skipping clone."
#fi

## Change to repo directory
#cd "/workspace/$REPO_NAME"

echo "=== ENVIRONMENT READY ==="
echo "Repository location: $(pwd)"
echo ""

# Function to add MCP servers using the Codex CLI
add_mcp_servers() {
    echo "Adding Slack MCP server..."
    codex mcp add slack /mcp-servers/slack_wrapper.sh "$CONFIG_FILE" "$EVENT_HISTORY_PATH"

    echo "Adding Linear MCP server..."
    codex mcp add linear /mcp-servers/linear_wrapper.sh "$CONFIG_FILE" "$EVENT_HISTORY_PATH"

    echo "Verifying MCP servers..."
    codex mcp list
    echo ""
}

# Get all questions from config
QUESTION_COUNT=$(yq eval '.benchmark.questions | length' "$CONFIG_FILE")
echo "Found $QUESTION_COUNT questions to process"
echo ""

# Process each question sequentially
for i in $(seq 0 $((QUESTION_COUNT - 1))); do
    QUESTION=$(yq eval ".benchmark.questions[$i]" "$CONFIG_FILE")

    echo "=========================================="
    echo "Processing Question $((i + 1))/$QUESTION_COUNT"
    echo "=========================================="
    echo "Question: $QUESTION"
    echo ""

    # Add MCP servers for this question
    add_mcp_servers

    # Create question-specific log file
    QUESTION_LOG_FILE="$QUESTIONS_DIR/question_$((i + 1)).log"

    # Ask the question
    echo "Asking Codex..."
    codex exec --skip-git-repo-check "$QUESTION" 2>&1 | tee "$QUESTION_LOG_FILE"

    echo ""
    echo "Question $((i + 1)) completed. Log saved to: $QUESTION_LOG_FILE"

    # Clean up MCP servers after question
    echo "Removing MCP servers..."
    codex mcp remove slack 2>/dev/null || true
    codex mcp remove linear 2>/dev/null || true
    echo ""

    # Small delay between questions
    sleep 5
done

echo "=========================================="
echo "All questions processed!"
echo "=========================================="
echo ""

# Create summary file in config directory
SUMMARY_FILE="$CONFIG_LOG_DIR/summary.txt"
echo "Benchmark Run Summary" > "$SUMMARY_FILE"
echo "=====================" >> "$SUMMARY_FILE"
echo "" >> "$SUMMARY_FILE"
echo "Configuration: $CONFIG_NAME" >> "$SUMMARY_FILE"
echo "Timestamp: $TIMESTAMP" >> "$SUMMARY_FILE"
echo "Run Date: $(date)" >> "$SUMMARY_FILE"
echo "Total Questions: $QUESTION_COUNT" >> "$SUMMARY_FILE"
echo "" >> "$SUMMARY_FILE"
echo "Questions and Expected Answers:" >> "$SUMMARY_FILE"
echo "===============================" >> "$SUMMARY_FILE"

for i in $(seq 0 $((QUESTION_COUNT - 1))); do
    QUESTION=$(yq eval ".benchmark.questions[$i]" "$CONFIG_FILE")
    EXPECTED_ANSWER=$(yq eval ".benchmark.expected_answers[$i]" "$CONFIG_FILE")
    echo "" >> "$SUMMARY_FILE"
    echo "Question $((i + 1)):" >> "$SUMMARY_FILE"
    echo "$QUESTION" >> "$SUMMARY_FILE"
    echo "" >> "$SUMMARY_FILE"
    echo "Expected Answer:" >> "$SUMMARY_FILE"
    echo "$EXPECTED_ANSWER" >> "$SUMMARY_FILE"
    echo "" >> "$SUMMARY_FILE"
    echo "Log File: questions/question_$((i + 1)).log" >> "$SUMMARY_FILE"
    echo "---" >> "$SUMMARY_FILE"
done

echo "" >> "$SUMMARY_FILE"
echo "Directory Structure:" >> "$SUMMARY_FILE"
echo "====================" >> "$SUMMARY_FILE"
echo "${CONFIG_NAME}_${TIMESTAMP}/" >> "$SUMMARY_FILE"
echo "├── summary.txt (this file)" >> "$SUMMARY_FILE"
echo "└── questions/" >> "$SUMMARY_FILE"
for i in $(seq 1 $QUESTION_COUNT); do
    if [ $i -eq $QUESTION_COUNT ]; then
        echo "    └── question_${i}.log" >> "$SUMMARY_FILE"
    else
        echo "    ├── question_${i}.log" >> "$SUMMARY_FILE"
    fi
done

echo ""
echo "Summary saved to: $SUMMARY_FILE"
echo "Questions saved to: $QUESTIONS_DIR"
echo "Config directory: $CONFIG_LOG_DIR"
echo ""
echo "========================================"
echo "Benchmark Complete: $CONFIG_NAME"
echo "========================================"