#!/bin/bash
# PAM Processing Script for LoCoMo
# Phase 2: Process conversation history and create memory structure

set -e

SAMPLE_ID="${1:-sample_0}"
LOG_DIR="${2:-/task_logs}"

CONTEXT_DIR="${SAMPLE_ID}_context_context"
PROCESSING_LOG_FILE="$LOG_DIR/processing.log"

mkdir -p "$LOG_DIR"

echo "========================================"
echo "PAM Processing: Conversation History"
echo "========================================"
echo ""

# Build the processing prompt for LoCoMo conversations
PROCESSING_PROMPT="You are PAM (Proactive AI Manager).

Your task is to process and organize conversation history data from LoCoMo (Long Context Memory) benchmark according to the PAM Memory Agent Guide structure.

## IMPORTANT: Understanding LoCoMo Data

LoCoMo contains **multi-session conversations** between two people. Unlike Slack/Linear events, these are personal dialogues that occur over multiple days/sessions. Each conversation session has:
- A date/timestamp (when the conversation happened)
- Multiple turns between two speakers
- Shared information, experiences, events, plans, and personal details

Files available in your workspace:
- /workspace/INIT.md - PAM Memory Agent Guide
- /workspace/init.py - Structure generator script (already run)
- /workspace/INTRO_TEMPLATE.md - Template for context
- /workspace/CLAUDE.md - Your system context
- /workspace/${CONTEXT_DIR}/ - PAM folder structure (created for you)

Files in /workspace/unsorted/ (conversation data):
- conversation_history.md - Full conversation in markdown format
- metadata.json - Session metadata (speakers, dates, session count)
- session_*.json - Individual session data files
- speakers.json - Speaker information

## PROCESSING INSTRUCTIONS FOR CONVERSATIONS

### Step 1: Read and understand the conversation structure
Read /workspace/unsorted/metadata.json and /workspace/unsorted/conversation_history.md to understand:
- Who are the two speakers
- How many sessions/conversations occurred
- The timeline of conversations

### Step 2: Create Person Profiles
For EACH speaker, create a profile in: /workspace/${CONTEXT_DIR}/02_people/
Filename: [speaker_name_lowercase].md

Include:
- Name and any personal details mentioned (age, location, occupation, etc.)
- Key life events discussed
- Relationships mentioned
- Hobbies, interests, activities
- Important dates mentioned

### Step 3: Create Session Digests (like Daily Digests)
For EACH conversation session, create a file in: /workspace/${CONTEXT_DIR}/09_activity_streams/daily_digests/
Filename: session_[number]_[date].md

Include:
- Session date
- Topics discussed
- Key facts shared by each speaker
- Events mentioned (past, present, future plans)
- Any decisions or plans made

### Step 4: Create Topic/Event Files
For significant topics, events, or activities discussed, create files in: /workspace/${CONTEXT_DIR}/09_activity_streams/linear_objects/
Filename: [topic_or_event_snake_case].md

Examples:
- If they discuss a job/career, create: career_counseling.md
- If they discuss a trip, create: camping_trip_june.md
- If they discuss a hobby, create: pottery_class.md

Track:
- What was discussed about this topic
- When it was mentioned
- Which speaker mentioned it
- Timeline (when did it happen or will happen)

### Step 5: Create Timeline of Events
Create /workspace/${CONTEXT_DIR}/09_activity_streams/timeline.md with:
- Chronological list of all events mentioned in conversations
- Include past events (things that happened before)
- Include future plans (things they plan to do)
- Reference the session where each event was mentioned

### Step 6: Create Summary
Create /workspace/processed_data.md with:
- Overview of the conversation (who, how many sessions, date range)
- Key facts about each speaker
- Important events and their dates
- Relationships between speakers
- Any patterns or recurring topics

## KEY DIFFERENCES FROM SLACK/LINEAR

1. **No ticket IDs**: Events are identified by topic/description, not IDs
2. **Personal conversations**: Focus on personal details, relationships, life events
3. **Temporal information**: Pay attention to dates, times, and temporal references (\"last week\", \"next month\", \"4 years ago\")
4. **Multi-session context**: Information builds across sessions - later sessions reference earlier ones

## OUTPUT VERIFICATION
After processing, list the files you created in each directory:
- 02_people/
- 09_activity_streams/daily_digests/
- 09_activity_streams/linear_objects/

Start now. Read the files and process them systematically."

echo "Asking Claude to process conversation history..."
cd /workspace
claude --verbose -p "$PROCESSING_PROMPT" --allowedTools "Read(*)" "Edit(*)" "Write(*)" "Bash(*)" < /dev/null 2>&1 | tee "$PROCESSING_LOG_FILE"

echo ""
echo "Processing phase completed. Log saved to: $PROCESSING_LOG_FILE"
echo ""

# Verification
echo "========================================"
echo "Verifying Created Files"
echo "========================================"

VERIFY_LOG="$LOG_DIR/verification.log"

echo "Checking directory structure..." | tee "$VERIFY_LOG"

echo "=== 02_people/ ===" | tee -a "$VERIFY_LOG"
ls -la /workspace/${CONTEXT_DIR}/02_people/ 2>&1 | tee -a "$VERIFY_LOG" || echo "Directory not found"

echo "" | tee -a "$VERIFY_LOG"
echo "=== 09_activity_streams/daily_digests/ ===" | tee -a "$VERIFY_LOG"
ls -la /workspace/${CONTEXT_DIR}/09_activity_streams/daily_digests/ 2>&1 | tee -a "$VERIFY_LOG" || echo "Directory not found"

echo "" | tee -a "$VERIFY_LOG"
echo "=== 09_activity_streams/linear_objects/ ===" | tee -a "$VERIFY_LOG"
ls -la /workspace/${CONTEXT_DIR}/09_activity_streams/linear_objects/ 2>&1 | tee -a "$VERIFY_LOG" || echo "Directory not found"

echo "" | tee -a "$VERIFY_LOG"
echo "=== processed_data.md exists? ===" | tee -a "$VERIFY_LOG"
if [ -f /workspace/processed_data.md ]; then
    echo "YES - processed_data.md found" | tee -a "$VERIFY_LOG"
    echo "First 30 lines:" | tee -a "$VERIFY_LOG"
    head -30 /workspace/processed_data.md | tee -a "$VERIFY_LOG"
else
    echo "NO - processed_data.md NOT FOUND" | tee -a "$VERIFY_LOG"
fi

echo ""
echo "Verification complete. Log saved to: $VERIFY_LOG"

# Clean up unsorted
echo ""
echo "Cleaning up unsorted folder..."
rm -rf /workspace/unsorted
echo "Unsorted folder removed"

echo ""
echo "========================================"
echo "PAM Processing Complete"
echo "========================================"
