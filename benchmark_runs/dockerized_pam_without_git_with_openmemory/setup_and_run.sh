#!/bin/bash

CONFIG_FILE="${1:-/benchmark_data/test_configs/config_1.yaml}"

# Extract config name from path
CONFIG_NAME=$(basename "$CONFIG_FILE" .yaml)
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Create organized directory structure for this config
# This will appear in outputs/ on the host
CONFIG_LOG_DIR="/workspace/logs/${CONFIG_NAME}_${TIMESTAMP}"
QUESTIONS_DIR="$CONFIG_LOG_DIR/questions"
MEMORY_DIR="$CONFIG_LOG_DIR/memory_snapshots"
mkdir -p "$QUESTIONS_DIR" "$MEMORY_DIR"

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

# Wait for OpenMemory to be ready
echo "Waiting for OpenMemory API..."
MAX_RETRIES=30
RETRY_COUNT=0
until curl -sf ${OPENMEMORY_URL:-http://openmemory-api:8765}/docs > /dev/null 2>&1; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        echo "ERROR: OpenMemory API failed to start"
        exit 1
    fi
    echo "Waiting for OpenMemory... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 2
done
echo "OpenMemory API is ready!"
echo ""

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

echo "=== ENVIRONMENT READY ==="

# Function to add MCP servers
add_mcp_servers() {
    echo "Adding Slack MCP server..."
    claude mcp add slack /mcp-servers/slack_wrapper.sh "$CONFIG_FILE" "$EVENT_HISTORY_PATH"

    echo "Adding Linear MCP server..."
    claude mcp add linear /mcp-servers/linear_wrapper.sh "$CONFIG_FILE" "$EVENT_HISTORY_PATH"

    echo "Adding OpenMemory MCP server..."
#    claude mcp add --transport sse openmemory "http://openmemory-api:8765/mcp/claude/sse/${USER_ID}"
    claude mcp add --transport sse openmemory "${OPENMEMORY_URL:-http://openmemory-api:8765}/mcp/claude/sse/${USER_ID}"

    echo "Verifying MCP servers..."
    claude mcp list
    echo ""
}

# Function to backup current memories using OpenMemory API
backup_memories() {
    local snapshot_file="$1"
    echo "Backing up memories to: $snapshot_file"

    curl -s -X POST "${OPENMEMORY_URL:-http://openmemory-api:8765}/api/v1/backup/export" \
        -H "Content-Type: application/json" \
        -d "{
            \"user_id\": \"${USER_ID}\",
            \"include_vectors\": false
        }" \
        -o "$snapshot_file" 2>/dev/null || echo "{\"error\": \"backup failed\"}" > "$snapshot_file"
}

# Function to clear memories using OpenMemory API
clear_memories() {
    echo "Clearing all memories for user: ${USER_ID}"

    # Get all memory IDs (with pagination support)
    local page=1
    local all_memory_ids="[]"

    while true; do
        local memories_response=$(curl -s "${OPENMEMORY_URL:-http://openmemory-api:8765}/api/v1/memories/?user_id=${USER_ID}&page=${page}&size=100")

        # Extract memory IDs and append to all_memory_ids
        local page_ids=$(echo "$memories_response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    ids = [item['id'] for item in data.get('items', [])]
    print(json.dumps(ids))
except:
    print('[]')
")

        # Check if we got any IDs
        if [ "$page_ids" == "[]" ]; then
            break
        fi

        # Merge IDs
        all_memory_ids=$(echo "$all_memory_ids" "$page_ids" | python3 -c "
import sys, json
try:
    existing = json.loads(sys.argv[1])
    new = json.loads(sys.argv[2])
    existing.extend(new)
    print(json.dumps(existing))
except:
    print('[]')
" "$all_memory_ids" "$page_ids")

        page=$((page + 1))
    done

    if [ "$all_memory_ids" != "[]" ] && [ -n "$all_memory_ids" ]; then
        # Delete all memories using the batch delete endpoint
        curl -s -X DELETE "${OPENMEMORY_URL:-http://openmemory-api:8765}/api/v1/memories/" \
            -H "Content-Type: application/json" \
            -d "{
                \"memory_ids\": $all_memory_ids,
                \"user_id\": \"${USER_ID}\"
            }" 2>/dev/null

        local count=$(echo "$all_memory_ids" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))")
        echo "Cleared ${count} memories"
    else
        echo "No memories to clear"
    fi
}


# Get all questions from config
QUESTION_COUNT=$(yq eval '.benchmark.questions | length' "$CONFIG_FILE")

echo "Found $QUESTION_COUNT questions to process"
echo ""

# Backup initial state (should be empty)
backup_memories "$MEMORY_DIR/initial_state.zip"

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

    claude --verbose -p "$QUESTION" --allowedTools mcp__linear mcp__slack mcp__openmemory 2>&1 | tee -a "$QUESTION_LOG_FILE"

    echo ""
    echo "Question $((i + 1)) completed. Log saved to: $QUESTION_LOG_FILE"

    backup_memories "$MEMORY_DIR/after_question_$((i + 1)).json"

    # Clean up MCP servers after question
    echo "Removing MCP servers..."
    claude mcp remove slack 2>/dev/null || true
    claude mcp remove linear 2>/dev/null || true
    claude mcp remove openmemory 2>/dev/null || true
    echo ""

    # Small delay between questions
    sleep 5
done

echo "=========================================="
echo "All questions processed!"
echo "=========================================="
echo ""

# Backup final state
backup_memories "$MEMORY_DIR/final_state.zip"

# Clear memories for next run
clear_memories

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

echo "" >> "$SUMMARY_FILE"
echo "Directory Structure:" >> "$SUMMARY_FILE"
echo "====================" >> "$SUMMARY_FILE"
echo "${CONFIG_NAME}_${TIMESTAMP}/" >> "$SUMMARY_FILE"
echo "├── summary.txt (this file)" >> "$SUMMARY_FILE"
echo "├── memory_snapshots/" >> "$SUMMARY_FILE"
echo "│   ├── initial_state.zip" >> "$SUMMARY_FILE"
for i in $(seq 1 $QUESTION_COUNT); do
    echo "│   ├── after_question_${i}.zip" >> "$SUMMARY_FILE"
done
echo "│   └── final_state.zip" >> "$SUMMARY_FILE"
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
echo "Memory snapshots saved to: $MEMORY_DIR"
echo "Config directory: $CONFIG_LOG_DIR"
echo ""
echo "========================================"
echo "Benchmark Complete: $CONFIG_NAME"
echo "========================================"