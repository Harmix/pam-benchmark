#!/bin/bash

CONFIG_FILE="${1:-/benchmark_data/test_configs/config_1.yaml}"

# Extract config name from path
CONFIG_NAME=$(basename "$CONFIG_FILE" .yaml)
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Create organized directory structure for this config
# This will appear in outputs/ on the host
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
BRANCH=$(yq eval '.repository.branch' "$CONFIG_FILE")
COMMIT=$(yq eval '.repository.commit' "$CONFIG_FILE")
SYSTEM_PROMPT=$(yq eval '.agent.system_prompt' "$CONFIG_FILE")

# Get event history path
EVENT_HISTORY=$(yq eval '.benchmark.event_history' "$CONFIG_FILE")
EVENT_HISTORY_PATH="/benchmark_data/$EVENT_HISTORY"

echo "Repository URL: $REPO_URL"
echo "Repository Name: $REPO_NAME"
echo "Branch: $BRANCH"
if [ "$COMMIT" != "null" ]; then
    echo "Commit: $COMMIT"
fi
echo "Event History: $EVENT_HISTORY_PATH"
echo ""

# Test MCP servers can load data
echo "Testing Slack MCP server..."
timeout 15 /mcp-servers/slack_wrapper.sh "$CONFIG_FILE" "$EVENT_HISTORY_PATH" 2>&1 | head -20
echo ""

echo "Testing Linear MCP server..."
timeout 15 /mcp-servers/linear_wrapper.sh "$CONFIG_FILE" "$EVENT_HISTORY_PATH" 2>&1 | head -20
echo ""

# Clone repository
REPO_AVAILABLE=false
if [ ! -d "/workspace/$REPO_NAME" ]; then
    echo ""
    echo "Cloning repository..."
    cd /workspace

    # Attempt to clone with detailed error capture
    CLONE_OUTPUT=$(mktemp)
    set +e  # Don't exit on error
    timeout 150 git clone "$REPO_URL" "$REPO_NAME" > "$CLONE_OUTPUT" 2>&1
    CLONE_EXIT_CODE=$?
    set -e  # Re-enable exit on error

    # Display clone output
    cat "$CLONE_OUTPUT"

    echo ""
    echo "=== CLONE DIAGNOSTICS ==="
    echo "Git clone exit code: $CLONE_EXIT_CODE"
    echo "Repository directory exists: $([ -d "/workspace/$REPO_NAME" ] && echo 'YES' || echo 'NO')"
    if [ -d "/workspace/$REPO_NAME" ]; then
        echo "Directory contents: $(ls -la /workspace/$REPO_NAME | wc -l) items"
        echo "Is git repository: $([ -d "/workspace/$REPO_NAME/.git" ] && echo 'YES' || echo 'NO')"
    fi
    echo "=========================="
    echo ""

    # Check if clone actually succeeded despite exit code
    if [ -d "/workspace/$REPO_NAME/.git" ]; then
        echo "Repository cloned successfully (verified by .git directory)!"
        REPO_AVAILABLE=true
        cd "$REPO_NAME"

        # Checkout branch if needed
        if [ "$BRANCH" != "null" ] && [ "$BRANCH" != "" ]; then
            CURRENT_BRANCH=$(git branch --show-current)
            if [ "$CURRENT_BRANCH" != "$BRANCH" ]; then
                echo "Checking out branch: $BRANCH"
                if git checkout "$BRANCH" 2>&1; then
                    echo "Branch checked out successfully!"
                else
                    echo "WARNING: Failed to checkout branch $BRANCH"
                fi
            else
                echo "Already on branch: $BRANCH"
            fi
        fi

        # Checkout specific commit if specified
        if [ "$COMMIT" != "null" ] && [ "$COMMIT" != "" ]; then
            echo "Checking out commit: $COMMIT"
            if git checkout "$COMMIT" 2>&1; then
                echo "Commit checked out successfully!"
            else
                echo "WARNING: Failed to checkout commit $COMMIT, continuing with current state"
            fi
        fi
    else
        echo "ERROR: Clone failed - no .git directory found"
        echo "Git exit code was: $CLONE_EXIT_CODE"
        echo "Last 10 lines of clone output:"
        tail -10 "$CLONE_OUTPUT"
        REPO_AVAILABLE=false
        mkdir -p "/workspace/$REPO_NAME"
    fi

    rm -f "$CLONE_OUTPUT"
else
    echo ""
    echo "Repository already exists at /workspace/$REPO_NAME"
    REPO_AVAILABLE=true

    # Ensure we're on the right commit if specified
    if [ "$COMMIT" != "null" ]; then
        echo "Ensuring commit: $COMMIT"
        cd "/workspace/$REPO_NAME"
        git fetch origin 2>/dev/null || echo "WARNING: Could not fetch from remote"
        if git checkout "$COMMIT" 2>&1; then
            echo "Commit checked out successfully!"
        else
            echo "WARNING: Failed to checkout commit $COMMIT, continuing with current state"
        fi
    fi
fi

# Change to repo directory
cd "/workspace/$REPO_NAME"

echo "=== ENVIRONMENT READY ==="
echo "Repository location: /workspace/$REPO_NAME"
echo "Repository available: $REPO_AVAILABLE"
if [ "$COMMIT" != "null" ] && [ "$REPO_AVAILABLE" = true ]; then
    CURRENT_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
    echo "Current commit: $CURRENT_COMMIT"
fi
echo ""

# Function to add MCP servers
add_mcp_servers() {
    echo "Adding Slack MCP server..."
    claude mcp add slack /mcp-servers/slack_wrapper.sh "$CONFIG_FILE" "$EVENT_HISTORY_PATH"

    echo "Adding Linear MCP server..."
    claude mcp add linear /mcp-servers/linear_wrapper.sh "$CONFIG_FILE" "$EVENT_HISTORY_PATH"

    echo "Verifying MCP servers..."
    claude mcp list
    echo ""
}

# Get all questions from config
QUESTION_COUNT=$(yq eval '.benchmark.questions | length' "$CONFIG_FILE")

echo "Found $QUESTION_COUNT questions to process"
echo ""

# Process each question sequentially
for i in $(seq 0 $((QUESTION_COUNT - 1))); do
    QUESTION=$(yq eval ".benchmark.questions[$i]" "$CONFIG_FILE")
    EXPECTED_ANSWER=$(yq eval ".benchmark.expected_answers[$i]" "$CONFIG_FILE")

    echo "=========================================="
    echo "Processing Question $((i + 1))/$QUESTION_COUNT"
    echo "=========================================="
    echo "Question: $QUESTION"
    echo "Expected Answer: $EXPECTED_ANSWER"
    echo ""

    # Add MCP servers for this question
    add_mcp_servers

    # Create question-specific log file in questions subdirectory
    QUESTION_LOG_FILE="$QUESTIONS_DIR/question_$((i + 1)).log"

    # Ask the question
    echo "Asking Claude..."
    if [ "$REPO_AVAILABLE" = false ]; then
        echo "NOTE: Repository is not available. Claude will work with limited context." | tee -a "$QUESTION_LOG_FILE"
    fi

    claude --verbose -p "$QUESTION" --allowedTools mcp__linear mcp__slack 2>&1 | tee "$QUESTION_LOG_FILE"

    echo ""
    echo "Question $((i + 1)) completed. Log saved to: $QUESTION_LOG_FILE"

    # Clean up MCP servers after question
    echo "Removing MCP servers..."
    claude mcp remove slack 2>/dev/null || true
    claude mcp remove linear 2>/dev/null || true
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
echo "Repository Information:" >> "$SUMMARY_FILE"
echo "----------------------" >> "$SUMMARY_FILE"
echo "Name: $REPO_NAME" >> "$SUMMARY_FILE"
echo "URL: $REPO_URL" >> "$SUMMARY_FILE"
echo "Branch: $BRANCH" >> "$SUMMARY_FILE"
if [ "$COMMIT" != "null" ]; then
    echo "Commit: $COMMIT" >> "$SUMMARY_FILE"
fi
echo "Available: $REPO_AVAILABLE" >> "$SUMMARY_FILE"
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