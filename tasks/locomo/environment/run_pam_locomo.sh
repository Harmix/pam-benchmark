#!/bin/bash
# Main PAM Runner for LoCoMo Benchmark
# Orchestrates setup, processing, answering, and evaluation phases
#
# Debug mode (PAM_DEBUG=true):
#   Skips memory creation (Phase 1 & 2) and answers questions directly.
#   Useful for testing the answer extraction and evaluation logic.

set -e

# Configuration
DATA_FILE="${DATA_FILE:-/task_data/data/locomo10.json}"
SAMPLE_INDEX="${SAMPLE_INDEX:-0}"
MAX_QUESTIONS="${MAX_QUESTIONS:-0}"
PAM_DEBUG="${PAM_DEBUG:-false}"

# Get sample ID from data
SAMPLE_ID=$(python3 -c "import json; print(json.load(open('$DATA_FILE'))[$SAMPLE_INDEX].get('sample_id', 'sample_$SAMPLE_INDEX'))")

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_DIR="/task_logs/${SAMPLE_ID}_${TIMESTAMP}"

# Record start time
EXECUTION_START_TIME=$(date +%s.%N)

echo "========================================"
echo "PAM LoCoMo Benchmark Runner"
echo "========================================"
echo "Sample ID: $SAMPLE_ID"
echo "Sample Index: $SAMPLE_INDEX"
echo "Data File: $DATA_FILE"
echo "Log Directory: $LOG_DIR"
echo "Max Questions: ${MAX_QUESTIONS:-all}"
echo "Experiment Name: ${EXPERIMENT_NAME:-not set}"
echo "PAM Debug Mode: $PAM_DEBUG"
echo ""

mkdir -p "$LOG_DIR"

# Source secrets if available
if [ -f /workspace/secrets.env ]; then
    set -a
    source /workspace/secrets.env
    set +a
    echo "Loaded secrets from /workspace/secrets.env"
fi

# ========================================
# Debug Mode: Skip memory creation
# ========================================
if [ "$PAM_DEBUG" = "true" ] || [ "$PAM_DEBUG" = "1" ]; then
    echo ""
    echo "========================================"
    echo "DEBUG MODE: Skipping memory creation"
    echo "========================================"
    echo ""
    
    # Just extract questions for answering
    echo "Extracting questions only..."
    mkdir -p /workspace/unsorted
    python3 /task_data/pam_utils.py questions \
        --data-file "$DATA_FILE" \
        --sample-index "$SAMPLE_INDEX" \
        --questions-file /workspace/questions.json
    
    # Create a minimal context directory for Claude to reference
    CONTEXT_DIR="${SAMPLE_ID}_context_context"
    mkdir -p "/workspace/${CONTEXT_DIR}"
    
    # Create a simple processed_data.md with raw conversation
    echo "Creating minimal context from raw conversation..."
    python3 << EOF
import json

with open('$DATA_FILE', 'r') as f:
    data = json.load(f)

sample = data[$SAMPLE_INDEX]
conv = sample.get('conversation', {})
speaker_a = conv.get('speaker_a', 'Speaker A')
speaker_b = conv.get('speaker_b', 'Speaker B')

# Create a simple summary
with open('/workspace/processed_data.md', 'w') as f:
    f.write(f"# Conversation Summary (DEBUG MODE)\\n\\n")
    f.write(f"**Participants:** {speaker_a} and {speaker_b}\\n\\n")
    f.write(f"**Note:** This is DEBUG mode - no memory structure was created.\\n")
    f.write(f"Claude will answer questions based on the raw conversation data.\\n\\n")
    
    # Add raw conversation
    f.write("## Raw Conversation\\n\\n")
    session_num = 1
    while f'session_{session_num}' in conv:
        session_key = f'session_{session_num}'
        date_key = f'session_{session_num}_date_time'
        session_data = conv.get(session_key, [])
        session_date = conv.get(date_key, f'Session {session_num}')
        
        f.write(f"### Session {session_num} - {session_date}\\n\\n")
        for turn in session_data:
            speaker = turn.get('speaker', 'Unknown')
            text = turn.get('text', '')
            f.write(f"**{speaker}:** {text}\\n\\n")
        session_num += 1

print("Created /workspace/processed_data.md with raw conversation")
EOF
    
else
    # ========================================
    # Phase 1: Setup
    # ========================================
    echo ""
    echo "======================================== PHASE 1: SETUP ========================================"
    /task_data/pam_setup.sh "$SAMPLE_ID" "$DATA_FILE" "$SAMPLE_INDEX"

    # ========================================
    # Phase 2: Process Conversation History
    # ========================================
    echo ""
    echo "======================================== PHASE 2: PROCESSING ========================================"
    sleep 3
    /task_data/pam_process.sh "$SAMPLE_ID" "$LOG_DIR"
fi

# ========================================
# Phase 3: Answer Questions
# ========================================
echo ""
echo "======================================== PHASE 3: ANSWERING ========================================"
sleep 3

# Optionally limit questions
if [ "$MAX_QUESTIONS" -gt 0 ]; then
    echo "Limiting to first $MAX_QUESTIONS questions..."
    python3 << EOF
import json
with open('/workspace/questions.json', 'r') as f:
    questions = json.load(f)
questions = questions[:$MAX_QUESTIONS]
with open('/workspace/questions.json', 'w') as f:
    json.dump(questions, f, indent=2)
print(f"Limited to {len(questions)} questions")
EOF
fi

/task_data/pam_answer.sh "$SAMPLE_ID" "$LOG_DIR" "/workspace/questions.json"

# ========================================
# Calculate Execution Time
# ========================================
EXECUTION_END_TIME=$(date +%s.%N)
EXECUTION_DURATION=$(awk "BEGIN {printf \"%.2f\", $EXECUTION_END_TIME - $EXECUTION_START_TIME}")

echo "$EXECUTION_DURATION" > "$LOG_DIR/execution_time.txt"

# ========================================
# Phase 4: Evaluation & MongoDB Save
# ========================================
echo ""
echo "======================================== PHASE 4: EVALUATION ========================================"

PAM_ANSWERS_FILE="$LOG_DIR/pam_answers.json"
METRICS_FILE="$LOG_DIR/metrics.json"

if [ -f "$PAM_ANSWERS_FILE" ]; then
    echo "Evaluating PAM answers..."
    
    EVAL_ARGS="--pam-answers $PAM_ANSWERS_FILE"
    EVAL_ARGS="$EVAL_ARGS --data-file $DATA_FILE"
    EVAL_ARGS="$EVAL_ARGS --sample-index $SAMPLE_INDEX"
    EVAL_ARGS="$EVAL_ARGS --execution-time $EXECUTION_DURATION"
    EVAL_ARGS="$EVAL_ARGS --output-file $METRICS_FILE"
    
    if [ "$MAX_QUESTIONS" -gt 0 ]; then
        EVAL_ARGS="$EVAL_ARGS --max-questions $MAX_QUESTIONS"
    fi
    
    python3 /task_data/pam_evaluate.py $EVAL_ARGS
    
    echo ""
    echo "Evaluation complete. Metrics saved to: $METRICS_FILE"
else
    echo "Warning: PAM answers file not found at $PAM_ANSWERS_FILE"
    echo "Skipping evaluation"
fi

# ========================================
# Create Summary
# ========================================
SUMMARY_FILE="$LOG_DIR/summary.txt"
echo "PAM LoCoMo Benchmark Summary" > "$SUMMARY_FILE"
echo "=============================" >> "$SUMMARY_FILE"
echo "" >> "$SUMMARY_FILE"
echo "Sample ID: $SAMPLE_ID" >> "$SUMMARY_FILE"
echo "Sample Index: $SAMPLE_INDEX" >> "$SUMMARY_FILE"
echo "Timestamp: $TIMESTAMP" >> "$SUMMARY_FILE"
echo "Run Date: $(date)" >> "$SUMMARY_FILE"
echo "Execution Time: ${EXECUTION_DURATION} seconds" >> "$SUMMARY_FILE"
echo "Experiment Name: ${EXPERIMENT_NAME:-not set}" >> "$SUMMARY_FILE"
echo "" >> "$SUMMARY_FILE"
echo "Phases Completed:" >> "$SUMMARY_FILE"
echo "1. Setup: PAM folder structure created" >> "$SUMMARY_FILE"
echo "2. Processing: Conversation history processed" >> "$SUMMARY_FILE"
echo "3. Answering: Questions answered" >> "$SUMMARY_FILE"
echo "4. Evaluation: Metrics calculated and saved to MongoDB" >> "$SUMMARY_FILE"
echo "" >> "$SUMMARY_FILE"
echo "Output Files:" >> "$SUMMARY_FILE"
echo "- $LOG_DIR/processing.log" >> "$SUMMARY_FILE"
echo "- $LOG_DIR/verification.log" >> "$SUMMARY_FILE"
echo "- $LOG_DIR/pam_answers.json" >> "$SUMMARY_FILE"
echo "- $LOG_DIR/metrics.json" >> "$SUMMARY_FILE"
echo "- $LOG_DIR/questions/" >> "$SUMMARY_FILE"

# Add metrics to summary if available
if [ -f "$METRICS_FILE" ]; then
    echo "" >> "$SUMMARY_FILE"
    echo "Metrics:" >> "$SUMMARY_FILE"
    python3 -c "
import json
with open('$METRICS_FILE') as f:
    data = json.load(f)
metrics = data.get('metrics', {})
print(f\"  Overall Accuracy: {metrics.get('overall_accuracy', 'N/A')}\")
print(f\"  Correct: {metrics.get('correct_count', 'N/A')}/{metrics.get('total_questions', 'N/A')}\")
print(f\"  Incorrect: {metrics.get('incorrect_count', 'N/A')}\")
" >> "$SUMMARY_FILE"
fi

echo ""
echo "========================================"
echo "PAM LoCoMo Benchmark Complete!"
echo "========================================"
echo "Sample: $SAMPLE_ID"
echo "Execution time: ${EXECUTION_DURATION} seconds"
echo "Answers file: $LOG_DIR/pam_answers.json"
echo "Metrics file: $METRICS_FILE"
echo "Summary: $SUMMARY_FILE"
echo "========================================"
