#!/bin/bash
# PAM Answer Script for LoCoMo
# Phase 3: Answer questions using processed memory
# Uses batching (20 questions per Claude call) for faster execution

set -e

SAMPLE_ID="${1:-sample_0}"
LOG_DIR="${2:-/task_logs}"
QUESTIONS_FILE="${3:-/workspace/questions.json}"
BATCH_SIZE="${BATCH_SIZE:-20}"

CONTEXT_DIR="${SAMPLE_ID}_context_context"
QUESTIONS_DIR="$LOG_DIR/questions"
ANSWERS_FILE="$LOG_DIR/pam_answers.json"

mkdir -p "$QUESTIONS_DIR"

echo "========================================"
echo "PAM Answering: Questions Phase (Batched)"
echo "========================================"
echo ""

# Check if questions file exists
if [ ! -f "$QUESTIONS_FILE" ]; then
    echo "ERROR: Questions file not found: $QUESTIONS_FILE"
    exit 1
fi

# Get question count
QUESTION_COUNT=$(python3 -c "import json; print(len(json.load(open('$QUESTIONS_FILE'))))")
echo "Found $QUESTION_COUNT questions to answer"
echo "Batch size: $BATCH_SIZE"
echo ""

# Initialize answers JSON
echo "[]" > "$ANSWERS_FILE"

# Calculate number of batches
NUM_BATCHES=$(( (QUESTION_COUNT + BATCH_SIZE - 1) / BATCH_SIZE ))
echo "Processing in $NUM_BATCHES batch(es)"
echo ""

# Process questions in batches
for batch_num in $(seq 0 $((NUM_BATCHES - 1))); do
    START_IDX=$((batch_num * BATCH_SIZE))
    END_IDX=$((START_IDX + BATCH_SIZE - 1))
    if [ $END_IDX -ge $QUESTION_COUNT ]; then
        END_IDX=$((QUESTION_COUNT - 1))
    fi
    
    BATCH_QUESTIONS_COUNT=$((END_IDX - START_IDX + 1))
    
    echo "========================================"
    echo "Batch $((batch_num + 1)) / $NUM_BATCHES"
    echo "Questions $((START_IDX + 1)) to $((END_IDX + 1))"
    echo "========================================"
    echo ""
    
    BATCH_LOG_FILE="$QUESTIONS_DIR/batch_$((batch_num + 1)).log"
    
    # Build the questions list for this batch
    QUESTIONS_LIST=$(python3 << EOF
import json

with open('$QUESTIONS_FILE', 'r') as f:
    questions = json.load(f)

batch_questions = questions[$START_IDX:$((END_IDX + 1))]

output_lines = []
for i, q in enumerate(batch_questions):
    q_num = $START_IDX + i + 1
    output_lines.append(f"Q{q_num}: {q['question']}")

print("\n".join(output_lines))
EOF
)
    
    echo "Questions in this batch:"
    echo "$QUESTIONS_LIST"
    echo ""
    
    # Build the batch prompt
    BATCH_PROMPT="Based on the conversation history you've processed and organized in the PAM folder structure at /workspace/${CONTEXT_DIR}/ and the summary at /workspace/processed_data.md:

Answer ALL of the following questions. For each question, provide a concise answer.

$QUESTIONS_LIST

IMPORTANT INSTRUCTIONS:
1. Use ONLY information from the processed conversation data
2. Be concise - provide a direct answer (a few words or a short phrase)
3. If the answer involves a date or time, be specific
4. If the answer involves multiple items, list them separated by commas
5. If the information is not available in the conversation, say 'Not mentioned in the conversation'

FORMAT YOUR RESPONSE EXACTLY LIKE THIS (one answer per line):
A1: [your answer for Q1]
A2: [your answer for Q2]
A3: [your answer for Q3]
...and so on for all questions.

CRITICAL: You MUST provide an answer line (A1, A2, etc.) for EVERY question. Do not skip any.

Now answer all ${BATCH_QUESTIONS_COUNT} questions."

    # Ask Claude for the batch
    echo "Asking PAM (Claude) for batch of $BATCH_QUESTIONS_COUNT questions..." | tee "$BATCH_LOG_FILE"
    cd /workspace
    
    RESPONSE=$(claude --verbose -p "$BATCH_PROMPT" --allowedTools "Read(/workspace/**)" "Bash(ls:/workspace/*)" "Bash(cat:/workspace/*)" "Bash(find:/workspace/*)" "Bash(head:/workspace/*)" "Bash(tail:/workspace/*)" "Bash(tree:/workspace/*)" < /dev/null 2>&1 | tee -a "$BATCH_LOG_FILE")
    
    echo ""
    echo "Extracting answers from response..."
    
    # Parse the batch response and extract individual answers
    python3 << EOF
import json
import re

response = '''$RESPONSE'''

# Load current answers
with open('$ANSWERS_FILE', 'r') as f:
    answers = json.load(f)

# Load questions for reference
with open('$QUESTIONS_FILE', 'r') as f:
    all_questions = json.load(f)

# Extract answers using regex pattern A1:, A2:, etc.
# Handle various formats: "A1:", "A1.", "A1)", "Answer 1:"
answer_patterns = [
    r'A(\d+):\s*(.+?)(?=\nA\d+[:\.\)]|\n\n|\Z)',
    r'A(\d+)\.\s*(.+?)(?=\nA\d+[:\.\)]|\n\n|\Z)',
    r'Answer\s*(\d+):\s*(.+?)(?=\nAnswer\s*\d+|\n\n|\Z)',
]

extracted = {}

for pattern in answer_patterns:
    matches = re.findall(pattern, response, re.IGNORECASE | re.DOTALL)
    for match in matches:
        q_num = int(match[0])
        answer = match[1].strip()
        # Clean up the answer
        answer = answer.split('\n')[0].strip()  # Take first line only
        if q_num not in extracted or not extracted[q_num]:
            extracted[q_num] = answer

# Also try line-by-line extraction for simple format
for line in response.split('\n'):
    line = line.strip()
    match = re.match(r'^A(\d+)[:\.\)]\s*(.+)$', line, re.IGNORECASE)
    if match:
        q_num = int(match.group(1))
        answer = match.group(2).strip()
        if q_num not in extracted or not extracted[q_num]:
            extracted[q_num] = answer

# Process each question in the batch
for i in range($START_IDX, $END_IDX + 1):
    q_num = i + 1
    question = all_questions[i]['question']
    
    # Get the extracted answer or use fallback
    answer = extracted.get(q_num, "No answer extracted")
    
    answers.append({
        'question_num': q_num,
        'question': question,
        'pam_answer': answer
    })
    
    print(f"Q{q_num}: {question[:60]}...")
    print(f"A{q_num}: {answer}")
    print()

# Save updated answers
with open('$ANSWERS_FILE', 'w') as f:
    json.dump(answers, f, indent=2)

print(f"Extracted {len(extracted)} answers from batch")
EOF

    echo ""
    echo "Batch $((batch_num + 1)) completed. Log: $BATCH_LOG_FILE"
    echo ""
    
    # Small delay between batches
    if [ $batch_num -lt $((NUM_BATCHES - 1)) ]; then
        sleep 2
    fi
done

echo "========================================"
echo "All Questions Answered"
echo "========================================"
echo ""
echo "Answers saved to: $ANSWERS_FILE"
echo "Batch logs: $QUESTIONS_DIR"
echo ""

# Display summary
echo "Answer Summary:"
python3 -c "
import json
with open('$ANSWERS_FILE') as f:
    answers = json.load(f)
print(f'Total answers: {len(answers)}')
print()
for a in answers[:5]:
    print(f\"Q{a['question_num']}: {a['question'][:50]}...\")
    print(f\"A: {a['pam_answer'][:100]}\")
    print()
if len(answers) > 5:
    print(f'... and {len(answers) - 5} more answers')
"
