#!/bin/bash
# PAM Answer Script for LoCoMo
# Phase 3: Answer questions using processed memory
# Uses batching (50 questions per Claude call) for faster execution

set -e

SAMPLE_ID="${1:-sample_0}"
LOG_DIR="${2:-/task_logs}"
QUESTIONS_FILE="${3:-/workspace/questions.json}"
BATCH_SIZE="${BATCH_SIZE:-10}"

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
    BATCH_RESPONSE_FILE="$QUESTIONS_DIR/batch_$((batch_num + 1))_response.txt"
    
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
    
    # Run Claude and save response to file
    claude --verbose -p "$BATCH_PROMPT" --allowedTools "Read(/workspace/**)" "Bash(ls:/workspace/*)" "Bash(cat:/workspace/*)" "Bash(find:/workspace/*)" "Bash(head:/workspace/*)" "Bash(tail:/workspace/*)" "Bash(tree:/workspace/*)" < /dev/null 2>&1 | tee "$BATCH_LOG_FILE" > "$BATCH_RESPONSE_FILE"
    
    echo ""
    echo "Extracting answers from response..."
    
    # Parse the batch response and extract individual answers using the response file
    python3 << PYEOF
import json
import re

# Read response from file
with open('$BATCH_RESPONSE_FILE', 'r') as f:
    response = f.read()

print(f"Response length: {len(response)} characters")
print("")
print("=" * 60)
print("RAW RESPONSE (first 3000 chars):")
print("=" * 60)
print(response[:3000])
if len(response) > 3000:
    print(f"\n... [{len(response) - 3000} more characters] ...")
print("=" * 60)
print("")

# Load current answers
with open('$ANSWERS_FILE', 'r') as f:
    answers = json.load(f)

# Load questions for reference
with open('$QUESTIONS_FILE', 'r') as f:
    all_questions = json.load(f)

extracted = {}

# Method 1: Line by line extraction (most reliable)
for line in response.split('\n'):
    line = line.strip()
    # Match patterns like: A1: answer, A1. answer, A1) answer
    match = re.match(r'^A(\d+)[:\.\)]\s*(.+)$', line, re.IGNORECASE)
    if match:
        q_num = int(match.group(1))
        answer = match.group(2).strip()
        extracted[q_num] = answer
        
# Method 2: Look for "Answer X:" format
for line in response.split('\n'):
    line = line.strip()
    match = re.match(r'^Answer\s*(\d+)[:\.\)]\s*(.+)$', line, re.IGNORECASE)
    if match:
        q_num = int(match.group(1))
        answer = match.group(2).strip()
        if q_num not in extracted:
            extracted[q_num] = answer

# Method 3: Multi-line pattern matching
pattern = r'A(\d+)[:\.\)]\s*([^\n]+)'
matches = re.findall(pattern, response, re.IGNORECASE)
for match in matches:
    q_num = int(match[0])
    answer = match[1].strip()
    if q_num not in extracted:
        extracted[q_num] = answer

# Method 4: Look for numbered list format (1. answer, 2. answer)
if len(extracted) == 0:
    print("Trying numbered list format...")
    for line in response.split('\n'):
        line = line.strip()
        match = re.match(r'^(\d+)[:\.\)]\s*(.+)$', line)
        if match:
            q_num = int(match.group(1))
            answer = match.group(2).strip()
            # Adjust for batch offset
            if 1 <= q_num <= $BATCH_QUESTIONS_COUNT:
                actual_q_num = $START_IDX + q_num
                if actual_q_num not in extracted:
                    extracted[actual_q_num] = answer

print(f"Extracted {len(extracted)} answers")
if extracted:
    print(f"Question numbers found: {sorted(extracted.keys())}")

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
    
    status = "✓" if answer != "No answer extracted" else "✗"
    print(f"{status} Q{q_num}: {question[:50]}...")
    print(f"   A{q_num}: {answer[:80] if answer else 'No answer'}")

# Save updated answers
with open('$ANSWERS_FILE', 'w') as f:
    json.dump(answers, f, indent=2)

# Report extraction success rate
success_count = sum(1 for i in range($START_IDX, $END_IDX + 1) if (i + 1) in extracted)
print(f"\nExtraction success: {success_count}/{$BATCH_QUESTIONS_COUNT} questions")
PYEOF

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

total = len(answers)
extracted = sum(1 for a in answers if a['pam_answer'] != 'No answer extracted')
print(f'Total answers: {total}')
print(f'Successfully extracted: {extracted} ({100*extracted/total:.1f}%)')
print()
for a in answers[:5]:
    status = '✓' if a['pam_answer'] != 'No answer extracted' else '✗'
    print(f\"{status} Q{a['question_num']}: {a['question'][:50]}...\")
    print(f\"   A: {a['pam_answer'][:80]}\")
    print()
if len(answers) > 5:
    print(f'... and {len(answers) - 5} more answers')
"
