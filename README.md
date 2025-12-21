# PAM Benchmark: Performance Assessment for Agents in Dynamic Multi-Modal Environments

A comprehensive benchmark framework for evaluating AI agents' ability to operate in realistic, dynamic environments with multiple information sources (Linear, Slack, Git) and temporal reasoning requirements.

## Overview

PAM Benchmark tests agents' capabilities to:
- Navigate complex organizational communication across multiple platforms
- Correlate information from disparate sources (task tracking, team chat, version control)
- Reason about temporal sequences and causal relationships
- Extract precise technical details from ambiguous or incomplete information
- Handle realistic workplace scenarios with missing context and indirect references

## Key Features

**Multi-Platform Integration**
- Linear (task/project management)
- Slack (team communication)
- Git (code repository and history)
- Notification systems

**Dynamic Event Histories**
- Real-world temporal event sequences
- State transitions and dependencies
- Cross-platform information correlation
- Missing or incomplete context scenarios

**Diverse Evaluation Scenarios**
- Software development crisis situations (46 configurations)
- Technical debt investigations
- System architecture decisions
- Team coordination challenges
- Production incident analysis

## Benchmark Statistics

- **Total Configurations**: 46
- **Total Questions**: 143
- **Average Questions per Config**: 3.11
- **Agent Models Tested**: PAM, Claude Code, Codex
- **Evaluation Methods**: Exact match, LLM judge
- **Teams Represented**: 38 different team types
- **Average Team Size**: 3.37 members

## Repository Structure

```
.
├── test_configs/           # YAML configuration files (46 scenarios)
├── test_event_histories/   # JSON event data from Linear, Slack, Git
├── extract_questions.py    # Extract Q&A pairs from configs
├── analyze_event_histories.py  # Analyze event patterns
├── questions_answers.csv   # All Q&A pairs in CSV format
├── questions_answers.json  # All Q&A pairs in JSON format
├── quantitative_metadata.json  # Benchmark statistics
├── docker-compose.yaml     # Docker environment setup
└── requirements.txt        # Python dependencies
```

## Quick Start

**Install Dependencies at Benchmark runs (TODO)**
```bash
pip install -r requirements.txt
```

**Extract Questions and Answers**
```bash
python extract_questions.py
```

**Analyze Event Histories**
```bash
python analyze_event_histories.py
```

**Run Benchmark with Docker**
```bash
docker-compose up
```

## Configuration Format

Each benchmark scenario includes:
- Agent configuration (model, tools, max turns)
- Repository details (URL, branch)
- Team structure (members, roles)
- Questions and expected answers
- Evaluation criteria (exact match, LLM judge)
- Milestones and success metrics

## Question Types

**Direct Factual Queries**
- "What is the status of the oldest ticket that was once reassigned?"
- "How many tickets are currently done?"

**Cross-Platform Correlation**
- Linking Slack discussions to Linear tickets to Git commits
- Tracing decision flows across communication channels

**Temporal Reasoning**
- Understanding event sequences and causality
- Identifying root causes through timeline analysis

**Technical Archaeology**
- Git history investigation
- Code pattern analysis from vague descriptions
- Configuration debugging across systems

## Evaluation Metrics

- **Exact Match**: Case-insensitive string matching (32 configs use this)
- **LLM Judge**: GPT-4o evaluates answer quality (32 configs)
- 
## Tools Available to Agents

- `notification_server`: 32 configs
- `linear_server`: 32 configs
- `filesystem`: 32 configs
- `git`: 46 configs
- `slack_server`: 7 configs

## Platform Distribution

- Linear events: Primary task tracking
- Slack events: Team communication (7 scenarios)
- Git events: Code changes and history

## Agent Performance Considerations

Successful agents must:
1. Read event histories chronologically
2. Correlate timestamps across platforms
3. Track state transitions (todo → in_progress → done)
4. Handle indirect references and incomplete information
5. Reason about team dynamics and decision-making
6. Extract technical details from natural language

## Contributing

To add new benchmark scenarios:
1. Create YAML config in `test_configs/`
2. Generate corresponding event history JSON
3. Run extraction scripts to validate
4. Update statistics with `analyze_event_histories.py`

## License

MIT

## Citation

```bibtex
@misc{harmix_pam_benchmark,
  title={Harmix/PAM Benchmark: Performance Assessment for Agents in Dynamic Multi-Modal Environments},
  author={Vitalii Ratushnyi},
  year={2025}
}
```