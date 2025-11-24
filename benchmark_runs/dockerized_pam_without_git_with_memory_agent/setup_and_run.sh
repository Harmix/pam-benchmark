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

# CRITICAL: Clean up workspace but NOT logs (logs accumulate for evaluation)
echo "========================================"
echo "CLEANUP: Ensuring clean workspace"
echo "========================================"
rm -rf /workspace/unsorted
rm -rf /workspace/*.md
rm -rf /workspace/*.py
rm -rf /workspace/*_context/
mkdir -p /workspace/unsorted
echo "Workspace cleaned (logs preserved)"
echo ""

echo "========================================"
echo "Starting Benchmark: $CONFIG_NAME"
echo "========================================"
echo "Reading configuration from: $CONFIG_FILE"
echo "Logs directory: $CONFIG_LOG_DIR"
echo ""

# Parse YAML using yq
SYSTEM_PROMPT=$(yq eval '.agent.system_prompt' "$CONFIG_FILE")

# Copy PAM guide files to workspace root
echo "Copying PAM guide files to workspace..."
cp /benchmark_data/INIT.md /workspace/INIT.md
cp /benchmark_data/init.py /workspace/init.py
cp /benchmark_data/INTRO_TEMPLATE.md /workspace/INTRO_TEMPLATE.md
echo "PAM guide files copied to /workspace/"

# Copy CLAUDE.md to workspace
if [ -f "/benchmark_data/CLAUDE.md" ]; then
    cp /benchmark_data/CLAUDE.md /workspace/CLAUDE.md
    echo "CLAUDE.md copied to workspace"
fi
echo ""

# Extract Linear configuration to unsorted
echo "Extracting Linear configuration..."
LINEAR_CONFIG_FILE="/workspace/unsorted/linear_config.yaml"
echo "linear:" > "$LINEAR_CONFIG_FILE"
yq eval '.linear' "$CONFIG_FILE" | tail -n +2 >> "$LINEAR_CONFIG_FILE"
echo "Linear configuration saved to: $LINEAR_CONFIG_FILE"
echo ""

# Get event history path and copy to unsorted
EVENT_HISTORY=$(yq eval '.benchmark.event_history' "$CONFIG_FILE")
EVENT_HISTORY_PATH="/benchmark_data/$EVENT_HISTORY"

if [ -f "$EVENT_HISTORY_PATH" ]; then
    echo "Copying event history to unsorted folder..."
    cp "$EVENT_HISTORY_PATH" /workspace/unsorted/event_history.json
    echo "Event history copied to: /workspace/unsorted/event_history.json"

    # Show first few events for verification
    echo "First 3 events from history:"
    jq '.[0:3]' /workspace/unsorted/event_history.json | head -20
else
    echo "WARNING: Event history not found at $EVENT_HISTORY_PATH"
fi
echo ""

# Run init.py to create PAM folder structure
echo "========================================"
echo "Creating PAM Memory Folder Structure"
echo "========================================"
cd /workspace
python3 init.py "${CONFIG_NAME}_company" 2>&1 | head -20
echo ""
echo "PAM folder structure created at: /workspace/${CONFIG_NAME}_company_context/"
ls -la /workspace/*_context/ 2>/dev/null | head -10
echo ""

# Clear any Claude Code cache/state
echo "Clearing Claude Code cache..."
rm -rf /root/.claude/cache/* 2>/dev/null || true
rm -rf /tmp/claude* 2>/dev/null || true
echo "Claude cache cleared"
echo ""

# Get all questions from config
QUESTION_COUNT=$(yq eval '.benchmark.questions | length' "$CONFIG_FILE")

echo "Found $QUESTION_COUNT questions to process"
echo ""

# First, have Claude process the files and organize the data
echo "=========================================="
echo "Phase 1: Processing Event History"
echo "=========================================="

PROCESSING_LOG_FILE="$CONFIG_LOG_DIR/processing.log"

PROCESSING_PROMPT="You are PAM (Proactive AI Manager).

Your first task is to process and organize the event history data according to the PAM Memory Agent Guide structure.

Files available in your workspace:
- /workspace/INIT.md - PAM Memory Agent Guide
- /workspace/init.py - Structure generator script (already run)
- /workspace/INTRO_TEMPLATE.md - Company template
- /workspace/CLAUDE.md - Your system context
- /workspace/${CONFIG_NAME}_company_context/ - PAM folder structure (created for you)

Files in /workspace/unsorted/ (data for this specific config):
- event_history.json - Chronological list of Linear tickets and Slack messages
- linear_config.yaml - Linear team and user configuration

Process the event history following the PAM guide:
1. Read INIT.md to understand the PAM structure
2. Process event_history.json from the unsorted folder
3. Organize the data into the PAM folder structure at /workspace/${CONFIG_NAME}_company_context/:
   - Create daily digests in 09_activity_streams/daily_digests/
   - Create ticket objects in 09_activity_streams/linear_objects/
   - Update project statuses in 06_projects/
   - Track people mentioned in 02_people/
4. Create a summary file at /workspace/processed_data.md that tracks:
   * Each unique ticket by title
   * Current status of each ticket
   * Current lead/assignee
   * History of status changes
   * History of reassignments (when lead changes for same ticket)
5. Focus especially on tracking reassignments - when a ticket with the same title appears with a different 'lead' value

Use the PAM folder structure to properly organize the information, then confirm you're ready to answer questions about the data."

echo "Asking Claude to process event history..."
cd /workspace
claude --verbose -p "$PROCESSING_PROMPT" 2>&1 | tee "$PROCESSING_LOG_FILE"

echo ""
echo "Processing phase completed. Log saved to: $PROCESSING_LOG_FILE"
echo ""

# Small delay before questions
sleep 3

# Now process each question sequentially
echo "=========================================="
echo "Phase 2: Answering Questions"
echo "=========================================="
echo ""

for i in $(seq 0 $((QUESTION_COUNT - 1))); do
    QUESTION=$(yq eval ".benchmark.questions[$i]" "$CONFIG_FILE")
    EXPECTED_ANSWER=$(yq eval ".benchmark.expected_answers[$i]" "$CONFIG_FILE")

    echo "=========================================="
    echo "Processing Question $((i + 1))/$QUESTION_COUNT"
    echo "=========================================="
    echo "Question: $QUESTION"
    echo "Expected Answer: $EXPECTED_ANSWER"
    echo ""

    # Create question-specific log file in questions subdirectory
    QUESTION_LOG_FILE="$QUESTIONS_DIR/question_$((i + 1)).log"

    # Prepare the prompt for this specific question
    QUESTION_PROMPT="Based on the event history data you've processed and organized in the PAM folder structure at /workspace/${CONFIG_NAME}_company_context/:

Answer this specific question: $QUESTION

Provide a clear, concise answer based solely on the data you've processed. You can reference the organized data in the PAM folders or your summary at /workspace/processed_data.md."

    # Ask Claude
    echo "Asking Claude..." | tee -a "$QUESTION_LOG_FILE"

    # Use Claude to answer the question
    cd /workspace
    claude --verbose -p "$QUESTION_PROMPT" 2>&1 | tee "$QUESTION_LOG_FILE"

    echo ""
    echo "Question $((i + 1)) completed. Log saved to: $QUESTION_LOG_FILE"
    echo ""

    # Small delay between questions
    sleep 3
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
echo "Processing Phases:" >> "$SUMMARY_FILE"
echo "1. PAM Structure Creation: init.py" >> "$SUMMARY_FILE"
echo "2. Event History Processing: processing.log" >> "$SUMMARY_FILE"
echo "3. Question Answering: questions/question_*.log" >> "$SUMMARY_FILE"
echo "" >> "$SUMMARY_FILE"
echo "Workspace Structure:" >> "$SUMMARY_FILE"
echo "/workspace/" >> "$SUMMARY_FILE"
echo "├── INIT.md (PAM Guide)" >> "$SUMMARY_FILE"
echo "├── init.py (Structure generator)" >> "$SUMMARY_FILE"
echo "├── INTRO_TEMPLATE.md (Company template)" >> "$SUMMARY_FILE"
echo "├── CLAUDE.md (System context)" >> "$SUMMARY_FILE"
echo "├── ${CONFIG_NAME}_company_context/ (PAM folder structure)" >> "$SUMMARY_FILE"
echo "│   ├── 01_company/" >> "$SUMMARY_FILE"
echo "│   ├── 02_people/" >> "$SUMMARY_FILE"
echo "│   ├── 06_projects/" >> "$SUMMARY_FILE"
echo "│   ├── 09_activity_streams/" >> "$SUMMARY_FILE"
echo "│   └── ..." >> "$SUMMARY_FILE"
echo "└── unsorted/" >> "$SUMMARY_FILE"
echo "    ├── event_history.json (Config-specific data)" >> "$SUMMARY_FILE"
echo "    └── linear_config.yaml (Config-specific Linear setup)" >> "$SUMMARY_FILE"
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
echo "├── processing.log (initial data processing)" >> "$SUMMARY_FILE"
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