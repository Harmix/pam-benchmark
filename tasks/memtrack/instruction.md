# PAM Memtrack Task

This task evaluates an LLM agent's ability to process and answer questions based on event history data from Linear and Slack platforms using the PAM (Proactive AI Manager) memory agent framework.

## Task Overview

The agent must:
1. Process event history data (Linear tickets and Slack messages) from JSON files
2. Organize the data according to the PAM Memory Agent Guide structure
3. Answer questions about the processed data based on the organized information

## Task Structure

Each task instance includes:
- **YAML Configuration**: A config file from `test_configs/` that defines:
  - Agent configuration (model, tools, system prompt)
  - Benchmark questions to answer
  - Event history file reference
  - Expected answers (for evaluation)
- **Event History**: A JSON file from `test_event_histories/` containing chronological Linear tickets and Slack messages

## Environment Setup

The environment includes:
- Python 3.11 with system dependencies (curl, git, jq, build-essential)
- yq for YAML parsing
- Node.js and Claude Code (v2.0.76) for agent execution
- PAM guide files (INIT.md, init.py, INTRO_TEMPLATE.md, CLAUDE.md)

## Task Execution Flow

1. **Initialization**: The agent receives a YAML config file and corresponding event history JSON
2. **Memory Structure Creation**: Run `init.py` to create the PAM folder structure
3. **Data Processing**: Process event history JSON and organize it into:
   - Daily digests (chronological view)
   - Linear objects (ticket history)
   - Slack threads (channel conversations)
4. **Question Answering**: Answer questions based on the organized data

## Expected Output

For each question, the agent should provide:
- A clear, concise answer based on the processed data
- References to the organized data in the PAM folders when relevant

## Evaluation

The task is evaluated based on:
- Correctness of answers compared to expected answers
- Ability to process and organize event history data correctly
- Proper use of the PAM memory structure

