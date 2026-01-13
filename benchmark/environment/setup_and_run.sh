#!/bin/bash

CONFIG_FILE="${1:-/benchmark_data/test_configs/config_1.yaml}"
STUB_MODE="${STUB_MODE:-false}"
ORACLE_FILE="${ORACLE_FILE:-}"

# Extract config name from path
CONFIG_NAME=$(basename "$CONFIG_FILE" .yaml)
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Record start time for execution duration tracking
EXECUTION_START_TIME=$(date +%s.%N)

# Create organized directory structure for this config
# This will appear in outputs/ on the host
CONFIG_LOG_DIR="/benchmark_logs/${CONFIG_NAME}_${TIMESTAMP}"
QUESTIONS_DIR="$CONFIG_LOG_DIR/questions"
mkdir -p "$QUESTIONS_DIR"

# If stub mode is enabled, parse oracle file and exit
if [ "$STUB_MODE" = "true" ] || [ "$STUB_MODE" = "1" ]; then
    if [ -z "$ORACLE_FILE" ]; then
        echo "Error: STUB_MODE enabled but ORACLE_FILE not set"
        echo "Usage: STUB_MODE=true ORACLE_FILE=/path/to/oracle.txt $0 <config_file>"
        exit 1
    fi
    
    if [ ! -f "$ORACLE_FILE" ]; then
        echo "Error: Oracle file not found: $ORACLE_FILE"
        exit 1
    fi
    
    echo "========================================"
    echo "STUB MODE: Using oracle file"
    echo "========================================"
    echo "Config: $CONFIG_NAME"
    echo "Oracle file: $ORACLE_FILE"
    echo "Output directory: $CONFIG_LOG_DIR"
    echo ""
    
    # Use Python script to parse oracle file
    PARSE_SCRIPT="/benchmark_data/parse_oracle_stub.py"
    if [ -f "$PARSE_SCRIPT" ]; then
        python3 "$PARSE_SCRIPT" "$ORACLE_FILE" "$CONFIG_FILE" "$CONFIG_LOG_DIR" "$QUESTIONS_DIR"
    else
        echo "Error: Parser script not found at $PARSE_SCRIPT"
        exit 1
    fi
    
    echo ""
    echo "========================================"
    echo "Stub mode complete: $CONFIG_NAME"
    echo "========================================"
    exit 0
fi

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

# Fix permissions so Claude can create folders/files inside context
chmod -R 777 /workspace/${CONFIG_NAME}_company_context/
chmod 777 /workspace/unsorted/
echo "Permissions set for workspace directories"

echo ""
echo "PAM folder structure created at: /workspace/${CONFIG_NAME}_company_context/"
ls -la /workspace/*_context/ 2>/dev/null | head -10
echo ""

# Clear any Claude Code cache/state
#echo "Clearing Claude Code cache..."
#rm -rf /root/.claude/cache/* 2>/dev/null || true
#rm -rf /tmp/claude* 2>/dev/null || true
#echo "Claude cache cleared"
#echo ""

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

## PROCESSING INSTRUCTIONS

### Step 1: Read and parse event_history.json
Read the JSON file and separate events by platform (linear vs slack).

### Step 2: Process LINEAR events
For each Linear event:
1. Create/update a file in: /workspace/${CONFIG_NAME}_company_context/09_activity_streams/linear_objects/
2. Filename: [ticket_title_snake_case].md
3. Track: title, description, status, priority, lead, dates
4. If same ticket appears multiple times, UPDATE the existing file with new status/lead

### Step 3: Process SLACK events
For each Slack event:
1. Group messages by channel
2. Create ONE file per channel: /workspace/${CONFIG_NAME}_company_context/09_activity_streams/slack_threads/[channel_name].md
3. Format each file as chronological log:

\`\`\`markdown
# Channel: [channel_name]

## Messages

### [YYYY-MM-DD HH:MM] - @sender
message content

### [YYYY-MM-DD HH:MM] - @sender
message content
\`\`\`

### Step 4: Create Daily Digests
Group ALL events (Linear + Slack) by date.
Create files in: /workspace/${CONFIG_NAME}_company_context/09_activity_streams/daily_digests/
Filename: [YYYY-MM-DD].md
Include both Linear status changes AND Slack messages for that day.

### Step 5: Create Summary
Create /workspace/processed_data.md with:
- List of all unique tickets and their CURRENT status
- List of all channels found
- Count of messages per channel
- Any reassignments detected (lead changes on same ticket)

## OUTPUT VERIFICATION
After processing, list the files you created in each directory:
- 09_activity_streams/linear_objects/
- 09_activity_streams/slack_threads/
- 09_activity_streams/daily_digests/

Start now. Read the files and process them."

echo "Asking Claude to process event history..."
cd /workspace
claude --verbose -p "$PROCESSING_PROMPT" --allowedTools "Read(*)" "Edit(*)" "Write(*)" "Bash(*)" < /dev/null 2>&1 | tee "$PROCESSING_LOG_FILE"

echo "Cleaning up unsorted folder..."
rm -rf /workspace/unsorted
echo "Unsorted folder removed"
echo ""

echo ""
echo "Processing phase completed. Log saved to: $PROCESSING_LOG_FILE"
echo ""

# Small delay before questions
sleep 3

# VERIFICATION: Check what Claude created
# ========================================
echo "=========================================="
echo "Phase 1.5: Verifying Created Files"
echo "=========================================="

VERIFY_LOG_FILE="$CONFIG_LOG_DIR/verification.log"

echo "Checking directory structure..." | tee "$VERIFY_LOG_FILE"
echo "" | tee -a "$VERIFY_LOG_FILE"

echo "=== 09_activity_streams/daily_digests/ ===" | tee -a "$VERIFY_LOG_FILE"
ls -la /workspace/${CONFIG_NAME}_company_context/09_activity_streams/daily_digests/ 2>&1 | tee -a "$VERIFY_LOG_FILE"
echo "" | tee -a "$VERIFY_LOG_FILE"

echo "=== 09_activity_streams/linear_objects/ ===" | tee -a "$VERIFY_LOG_FILE"
ls -la /workspace/${CONFIG_NAME}_company_context/09_activity_streams/linear_objects/ 2>&1 | tee -a "$VERIFY_LOG_FILE"
echo "" | tee -a "$VERIFY_LOG_FILE"

echo "=== 09_activity_streams/slack_threads/ ===" | tee -a "$VERIFY_LOG_FILE"
ls -la /workspace/${CONFIG_NAME}_company_context/09_activity_streams/slack_threads/ 2>&1 | tee -a "$VERIFY_LOG_FILE"
echo "" | tee -a "$VERIFY_LOG_FILE"

echo "=== Full tree of 09_activity_streams ===" | tee -a "$VERIFY_LOG_FILE"
tree /workspace/${CONFIG_NAME}_company_context/09_activity_streams/ 2>&1 | tee -a "$VERIFY_LOG_FILE"
echo "" | tee -a "$VERIFY_LOG_FILE"

echo "=== processed_data.md exists? ===" | tee -a "$VERIFY_LOG_FILE"
if [ -f /workspace/processed_data.md ]; then
    echo "YES - processed_data.md found" | tee -a "$VERIFY_LOG_FILE"
    echo "First 50 lines:" | tee -a "$VERIFY_LOG_FILE"
    head -50 /workspace/processed_data.md | tee -a "$VERIFY_LOG_FILE"
else
    echo "NO - processed_data.md NOT FOUND" | tee -a "$VERIFY_LOG_FILE"
fi
echo "" | tee -a "$VERIFY_LOG_FILE"

echo "=== Count of files created ===" | tee -a "$VERIFY_LOG_FILE"
echo "Daily digests: $(find /workspace/${CONFIG_NAME}_company_context/09_activity_streams/daily_digests/ -type f 2>/dev/null | wc -l)" | tee -a "$VERIFY_LOG_FILE"
echo "Linear objects: $(find /workspace/${CONFIG_NAME}_company_context/09_activity_streams/linear_objects/ -type f 2>/dev/null | wc -l)" | tee -a "$VERIFY_LOG_FILE"
echo "Slack threads: $(find /workspace/${CONFIG_NAME}_company_context/09_activity_streams/slack_threads/ -type f 2>/dev/null | wc -l)" | tee -a "$VERIFY_LOG_FILE"
echo "" | tee -a "$VERIFY_LOG_FILE"

echo "Verification complete. Log saved to: $VERIFY_LOG_FILE"
echo ""

echo "Cleaning up unsorted folder..."
rm -rf /workspace/unsorted
echo "Unsorted folder removed"
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
#    EXPECTED_ANSWER=$(yq eval ".benchmark.expected_answers[$i]" "$CONFIG_FILE")

    echo "=========================================="
    echo "Processing Question $((i + 1))/$QUESTION_COUNT"
    echo "=========================================="
    echo "Question: $QUESTION"
#    echo "Expected Answer: $EXPECTED_ANSWER"
    echo ""

    # Create question-specific log file in questions subdirectory
    QUESTION_LOG_FILE="$QUESTIONS_DIR/question_$((i + 1)).log"

    # Prepare the prompt for this specific question
    QUESTION_PROMPT="Based on the event history data you've processed and organized in the PAM folder structure at /workspace/${CONFIG_NAME}_company_context/ and only that folder:

Answer this specific question: $QUESTION

Provide a clear, concise answer based solely on the data you've processed. You can reference the organized data in the PAM folders or your summary at /workspace/processed_data.md."

    # Ask Claude
    echo "Asking Claude..." | tee -a "$QUESTION_LOG_FILE"

    # Use Claude to answer the question
    cd /workspace
    claude --verbose -p "$QUESTION_PROMPT" --allowedTools "Read(/workspace/**)" "Bash(ls:/workspace/*)" "Bash(cat:/workspace/*)" "Bash(find:/workspace/*)" "Bash(head:/workspace/*)" "Bash(tail:/workspace/*)" "Bash(tree:/workspace/*)" < /dev/null 2>&1 | tee -a "$QUESTION_LOG_FILE"
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

# Record end time and calculate execution duration
EXECUTION_END_TIME=$(date +%s.%N)
# Calculate duration using awk (more portable than bc)
EXECUTION_DURATION=$(awk "BEGIN {printf \"%.2f\", $EXECUTION_END_TIME - $EXECUTION_START_TIME}")
EXECUTION_DURATION_SECONDS="$EXECUTION_DURATION"

# Add execution time to summary file
echo "" >> "$SUMMARY_FILE"
echo "Execution Statistics:" >> "$SUMMARY_FILE"
echo "====================" >> "$SUMMARY_FILE"
echo "Execution time: ${EXECUTION_DURATION_SECONDS} seconds" >> "$SUMMARY_FILE"

echo ""
echo "Summary saved to: $SUMMARY_FILE"
echo "Questions saved to: $QUESTIONS_DIR"
echo "Config directory: $CONFIG_LOG_DIR"
echo ""

echo "========================================"
echo "Benchmark Complete: $CONFIG_NAME"
echo "Execution time: ${EXECUTION_DURATION_SECONDS} seconds"
echo "========================================"

# Save execution time to a file for the evaluation script
echo "$EXECUTION_DURATION_SECONDS" > "$CONFIG_LOG_DIR/execution_time.txt"

# Run LLM Judge evaluation for this config immediately after completion
echo ""
echo "========================================"
echo "Running LLM Judge Evaluation"
echo "========================================"
echo ""

# Find evaluation script
EVAL_SCRIPT=""
POSSIBLE_EVAL_PATHS=(
    "/workspace/solution/llm_judge_eval.py"
    "/solution/llm_judge_eval.py"
    "./solution/llm_judge_eval.py"
    "solution/llm_judge_eval.py"
    "$(pwd)/solution/llm_judge_eval.py"
    "/workspace/llm_judge_eval.py"
)

for path in "${POSSIBLE_EVAL_PATHS[@]}"; do
    if [ -f "$path" ]; then
        EVAL_SCRIPT="$path"
        break
    fi
done

if [ -n "$EVAL_SCRIPT" ] && [ -f "$EVAL_SCRIPT" ]; then
    # Check if Python 3 is available
    if ! command -v python3 &> /dev/null; then
        echo "Warning: python3 not found, skipping evaluation"
    else
        # Check if OPENAI_API_KEY is available (required for evaluation)
        if [ -z "${OPENAI_API_KEY:-}" ]; then
            echo "Warning: OPENAI_API_KEY not set, skipping evaluation"
            echo "Note: Evaluation requires OPENAI_API_KEY to be set in secrets.env"
        else
            # Run evaluation script for this specific config
            # Pass execution time and experiment name
            echo "Evaluating config: $CONFIG_NAME"
            echo "Execution time: ${EXECUTION_DURATION_SECONDS} seconds"
            
            # Build command with experiment name if available
            EVAL_CMD=(
                python3 "$EVAL_SCRIPT"
                --output-dir /benchmark_logs
                --test-configs-dir /benchmark_data/test_configs
                --config "$CONFIG_NAME"
                --summary-only
            )
            
            # Add experiment name if available (from env or try to read from file)
            if [ -n "${EXPERIMENT_NAME:-}" ]; then
                echo "Experiment name: $EXPERIMENT_NAME"
                EVAL_CMD+=(--experiment-name "$EXPERIMENT_NAME")
            else
                # Try to read from a file if Harbor passed it via file
                EXPERIMENT_NAME_FILE="/workspace/solution/experiment_name.txt"
                if [ -f "$EXPERIMENT_NAME_FILE" ]; then
                    EXPERIMENT_NAME=$(cat "$EXPERIMENT_NAME_FILE" | head -1 | tr -d '\n\r')
                    if [ -n "$EXPERIMENT_NAME" ]; then
                        echo "Experiment name (from file): $EXPERIMENT_NAME"
                        EVAL_CMD+=(--experiment-name "$EXPERIMENT_NAME")
                    fi
                fi
            fi
            
            # Run with execution time and Harbor project name in environment
            # Harbor project name defaults to "benchmark" if not set
            EXPORT_EXECUTION_TIME="$EXECUTION_DURATION_SECONDS" \
            HARBOR_PROJECT_NAME="${HARBOR_PROJECT_NAME:-benchmark}" \
            "${EVAL_CMD[@]}"
            
            EVAL_EXIT_CODE=$?
            if [ $EVAL_EXIT_CODE -eq 0 ]; then
                echo ""
                echo "✓ Evaluation completed successfully for $CONFIG_NAME"
            else
                echo ""
                echo "⚠ Evaluation completed with exit code: $EVAL_EXIT_CODE for $CONFIG_NAME"
            fi
        fi
    fi
else
    echo "Warning: Evaluation script not found, skipping evaluation"
fi

echo ""
